import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.principal import Principal
from app.modules.knowledge.models import Chunk, Document, KnowledgeSource
from app.modules.llm.embeddings import Embedder

# Small ranking bonus for knowledge belonging to the app the chat was opened from.
ORIGIN_APP_BOOST = 0.05


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_uri: str | None
    source_name: str
    application_id: str | None
    heading: str | None
    content: str
    score: float


def acl_filter(principal: Principal) -> ColumnElement[bool]:
    """SQL condition: sources open to everyone, or sharing at least one of the caller's roles.

    Applied inside the vector query itself, so chunks the employee may not see are never
    loaded, never ranked and never reach the LLM.
    """
    return or_(
        func.cardinality(KnowledgeSource.acl_roles) == 0,
        KnowledgeSource.acl_roles.overlap(sorted(principal.roles)),
    )


async def search_knowledge(
    db: AsyncSession,
    embedder: Embedder,
    principal: Principal,
    query: str,
    *,
    top_k: int,
    min_score: float,
    origin_app_id: str | None = None,
) -> list[RetrievedChunk]:
    query_vector = await embedder.embed_query(query)
    distance = Chunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.document_id,
            Chunk.heading,
            Chunk.content,
            Document.title.label("document_title"),
            Document.uri.label("document_uri"),
            KnowledgeSource.name.label("source_name"),
            KnowledgeSource.application_id,
            (1 - distance).label("score"),
        )
        .join(Document, Chunk.document_id == Document.id)
        .join(KnowledgeSource, Document.source_id == KnowledgeSource.id)
        .where(acl_filter(principal))
        .order_by(distance)
        .limit(top_k * 3)
    )
    rows = (await db.execute(stmt)).all()
    results = [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            document_title=row.document_title,
            document_uri=row.document_uri,
            source_name=row.source_name,
            application_id=row.application_id,
            heading=row.heading,
            content=row.content,
            score=float(row.score),
        )
        for row in rows
        if row.score is not None and float(row.score) >= min_score
    ]

    def rank(result: RetrievedChunk) -> float:
        boost = ORIGIN_APP_BOOST if origin_app_id and result.application_id == origin_app_id else 0
        return result.score + boost

    results.sort(key=rank, reverse=True)
    return results[:top_k]
