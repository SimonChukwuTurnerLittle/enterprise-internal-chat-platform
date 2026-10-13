from typing import Any, Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import request_id_var
from app.modules.audit.models import AuditEvent
from app.modules.identity.principal import Principal

log = structlog.get_logger()

Outcome = Literal["success", "denied", "error"]


def record_audit(
    db: AsyncSession,
    *,
    action: str,
    outcome: Outcome = "success",
    principal: Principal | None = None,
    actor_subject: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    application_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session; it is persisted with the caller's commit.

    Never put message text, document content or tokens in `details`: audit records who did
    what to which resource, not the data itself.
    """
    event = AuditEvent(
        action=action,
        outcome=outcome,
        actor_subject=principal.subject if principal else actor_subject,
        actor_user_id=principal.user_id if principal else None,
        resource_type=resource_type,
        resource_id=resource_id,
        application_id=application_id,
        request_id=request_id_var.get(),
        details=details or {},
    )
    db.add(event)
    log.info(
        "audit",
        action=action,
        outcome=outcome,
        actor=event.actor_subject,
        resource_type=resource_type,
        resource_id=resource_id,
    )
