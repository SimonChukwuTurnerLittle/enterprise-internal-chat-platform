"""One chat turn: retrieve → build prompt → stream the answer → persist → audit.

Events are Server-Sent Events (SSE): see docs/api.md for the contract.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import anyio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.modules.audit.service import record_audit
from app.modules.chat.prompts import (
    FALLBACK_ANSWER,
    build_messages,
    format_host_context,
    retrieval_query,
)
from app.modules.conversations.models import Message
from app.modules.conversations.schemas import Citation, HostContext
from app.modules.identity.principal import Principal
from app.modules.knowledge.search import RetrievedChunk, search_knowledge
from app.modules.llm.chat import ChatMessage, ChatModel
from app.modules.llm.embeddings import Embedder

log = structlog.get_logger()

SNIPPET_CHARS = 300
GENERATION_FAILED = "Sorry, something went wrong. Please try again."


@dataclass(frozen=True)
class ChatTurn:
    principal: Principal
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    question: str
    history: list[ChatMessage]
    context: HostContext | None
    context_app_name: str | None
    origin_app_id: str | None


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            n=number,
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            source_name=chunk.source_name,
            heading=chunk.heading,
            uri=chunk.document_uri,
            snippet=chunk.content[:SNIPPET_CHARS],
            score=round(chunk.score, 4),
        )
        for number, chunk in enumerate(chunks, start=1)
    ]


def make_title(question: str, max_chars: int = 60) -> str:
    text = " ".join(question.split())
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "…"


async def _words(text: str) -> AsyncIterator[str]:
    for word in text.split(" "):
        yield word + " "


async def stream_chat_turn(
    turn: ChatTurn, settings: Settings, chat_model: ChatModel, embedder: Embedder
) -> AsyncIterator[str]:
    assistant_id = uuid.uuid4()
    started = time.perf_counter()
    parts: list[str] = []
    chunks: list[RetrievedChunk] = []
    citations: list[Citation] = []
    outcome = "success"

    yield sse(
        "message.start",
        {"message_id": str(assistant_id), "user_message_id": str(turn.user_message_id)},
    )
    async with get_sessionmaker()() as db:
        try:
            chunks = await search_knowledge(
                db,
                embedder,
                turn.principal,
                retrieval_query(turn.question, turn.history),
                top_k=settings.rag_top_k,
                min_score=settings.effective_rag_min_score,
                origin_app_id=turn.origin_app_id,
            )
            citations = build_citations(chunks)
            yield sse("citations", {"citations": [c.model_dump(mode="json") for c in citations]})

            if chunks:
                messages = build_messages(
                    question=turn.question,
                    history=turn.history,
                    chunks=chunks,
                    host_context=format_host_context(turn.context, turn.context_app_name),
                    organisation=settings.organisation_name,
                )
                stream = chat_model.stream(messages)
            else:
                # Nothing relevant the employee is allowed to see: answer deterministically
                # instead of letting the model improvise.
                stream = _words(FALLBACK_ANSWER)
            async for delta in stream:
                parts.append(delta)
                yield sse("token", {"text": delta})
        except Exception:
            outcome = "error"
            log.exception("chat.turn_failed", conversation_id=str(turn.conversation_id))
            yield sse("error", {"code": "generation_failed", "message": GENERATION_FAILED})
        except BaseException:  # client disconnected (cancellation / generator closed)
            outcome = "cancelled"
            raise
        finally:
            # Shielded so the write still happens when the request was cancelled.
            with anyio.CancelScope(shield=True):
                await _persist(
                    db, turn, assistant_id, parts, citations, chunks, outcome, chat_model, started
                )

    if outcome == "success":
        yield sse("message.end", {"message_id": str(assistant_id)})


async def _persist(
    db: AsyncSession,
    turn: ChatTurn,
    assistant_id: uuid.UUID,
    parts: list[str],
    citations: list[Citation],
    chunks: list[RetrievedChunk],
    outcome: str,
    chat_model: ChatModel,
    started: float,
) -> None:
    try:
        content = "".join(parts).strip()
        if content:
            db.add(
                Message(
                    id=assistant_id,
                    conversation_id=turn.conversation_id,
                    role="assistant",
                    content=content,
                    citations=[c.model_dump(mode="json") for c in citations],
                    meta={
                        "model": chat_model.name if chunks else "fallback",
                        "outcome": outcome,
                        "retrieval": [
                            {"chunk_id": str(c.chunk_id), "score": round(c.score, 4)}
                            for c in chunks
                        ],
                    },
                )
            )
        record_audit(
            db,
            action="chat.message",
            outcome="success" if outcome == "success" else "error",
            principal=turn.principal,
            resource_type="conversation",
            resource_id=str(turn.conversation_id),
            application_id=turn.origin_app_id,
            details={
                "result": outcome,
                "message_id": str(assistant_id),
                "documents": sorted({str(c.document_id) for c in chunks}),
                "grounded": bool(chunks),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        await db.commit()
    except Exception:
        log.exception("chat.persist_failed", conversation_id=str(turn.conversation_id))
