import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.audit.service import record_audit
from app.modules.conversations.models import Conversation
from app.modules.conversations.repository import (
    get_owned_conversation,
    list_conversations,
    list_messages,
)
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.modules.identity.deps import get_principal
from app.modules.identity.principal import Principal
from app.modules.registry.models import Application

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Conversation:
    if body.origin_app_id is not None:
        app = await db.get(Application, body.origin_app_id)
        if app is None or not app.enabled:
            raise HTTPException(status_code=422, detail="Unknown application")
    conversation = Conversation(
        user_id=principal.user_id, title=body.title, origin_app_id=body.origin_app_id
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationOut])
async def get_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Conversation]:
    return await list_conversations(db, principal, limit)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ConversationDetail:
    conversation = await get_owned_conversation(db, principal, conversation_id)
    messages = await list_messages(db, conversation.id)
    return ConversationDetail(
        **ConversationOut.model_validate(conversation).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Conversation:
    conversation = await get_owned_conversation(db, principal, conversation_id)
    conversation.title = body.title
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def archive_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Response:
    conversation = await get_owned_conversation(db, principal, conversation_id)
    conversation.archived_at = datetime.now(UTC)
    record_audit(
        db,
        action="conversation.archive",
        principal=principal,
        resource_type="conversation",
        resource_id=str(conversation.id),
    )
    await db.commit()
    return Response(status_code=204)
