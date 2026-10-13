import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.audit.models import AuditEvent
from app.modules.identity.deps import require_admin
from app.modules.identity.principal import Principal

router = APIRouter(prefix="/api/v1/admin/audit", tags=["admin"])


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    outcome: str
    actor_subject: str | None
    actor_user_id: uuid.UUID | None
    resource_type: str | None
    resource_id: str | None
    application_id: str | None
    request_id: str | None
    details: dict[str, Any]

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditEventOut])
async def list_audit_events(
    action: str | None = Query(default=None, max_length=100),
    actor_subject: str | None = Query(default=None, max_length=255),
    before_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor_subject:
        stmt = stmt.where(AuditEvent.actor_subject == actor_subject)
    if before_id:
        stmt = stmt.where(AuditEvent.id < before_id)
    return list((await db.scalars(stmt)).all())
