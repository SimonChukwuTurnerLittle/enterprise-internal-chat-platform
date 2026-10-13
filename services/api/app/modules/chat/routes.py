import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.ratelimit import enforce_rate_limit
from app.core.redis import get_redis
from app.modules.chat.service import ChatTurn, make_title, stream_chat_turn
from app.modules.conversations.models import Message
from app.modules.conversations.repository import get_owned_conversation, recent_messages
from app.modules.conversations.schemas import SendMessageRequest
from app.modules.identity.deps import get_principal
from app.modules.identity.principal import Principal
from app.modules.llm.chat import ChatMessage, ChatModel
from app.modules.llm.embeddings import Embedder
from app.modules.llm.factory import get_chat_model, get_embedder
from app.modules.registry.models import Application

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


@router.post(
    "/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
    chat_model: ChatModel = Depends(get_chat_model),
    embedder: Embedder = Depends(get_embedder),
) -> StreamingResponse:
    """Send a user message and stream the assistant's answer as Server-Sent Events."""
    question = body.content.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message is empty")
    if len(question) > settings.max_message_chars:
        raise HTTPException(
            status_code=422, detail=f"Message exceeds {settings.max_message_chars} characters"
        )
    conversation = await get_owned_conversation(db, principal, conversation_id)
    await enforce_rate_limit(
        redis, f"chat:{principal.subject}", settings.rate_limit_messages_per_minute
    )

    # Context comes from the browser: keep it only if it names a known, enabled application.
    context = body.context
    context_app: Application | None = None
    if context and context.app_id:
        context_app = await db.get(Application, context.app_id)
        if context_app is None or not context_app.enabled:
            context = context.model_copy(update={"app_id": None})
            context_app = None

    history = [
        ChatMessage(m.role, m.content)  # type: ignore[arg-type]
        for m in await recent_messages(db, conversation.id, settings.history_messages)
    ]
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=question,
        meta={"context": context.model_dump(exclude_none=True)} if context else {},
    )
    db.add(user_message)
    if conversation.title is None:
        conversation.title = make_title(question)
    conversation.updated_at = datetime.now(UTC)
    await db.commit()

    turn = ChatTurn(
        principal=principal,
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        question=question,
        history=history,
        context=context,
        context_app_name=context_app.name if context_app else None,
        origin_app_id=conversation.origin_app_id or (context_app.id if context_app else None),
    )
    return StreamingResponse(
        stream_chat_turn(turn, settings, chat_model, embedder),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
