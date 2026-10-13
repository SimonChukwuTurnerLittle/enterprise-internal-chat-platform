import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models import Conversation, Message
from app.modules.identity.principal import Principal


async def get_owned_conversation(
    db: AsyncSession, principal: Principal, conversation_id: uuid.UUID
) -> Conversation:
    """Return the conversation only if it belongs to the caller. Other users' conversations
    get a 404, not a 403, so their existence is not revealed."""
    conversation = await db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.user_id != principal.user_id
        or conversation.archived_at is not None
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def list_conversations(
    db: AsyncSession, principal: Principal, limit: int
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == principal.user_id, Conversation.archived_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def list_messages(db: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq)
    return list((await db.scalars(stmt)).all())


async def recent_messages(
    db: AsyncSession, conversation_id: uuid.UUID, limit: int
) -> list[Message]:
    """The last `limit` messages, oldest first."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(limit)
    )
    return list(reversed((await db.scalars(stmt)).all()))
