import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    """Local record of an IdP identity. The IdP stays the source of truth for roles."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def upsert_user(
    db: AsyncSession, subject: str, email: str | None, display_name: str | None
) -> uuid.UUID:
    """Insert or refresh the user row for an IdP subject and return its id. Caller commits."""
    stmt = (
        insert(User)
        .values(id=uuid.uuid4(), subject=subject, email=email, display_name=display_name)
        .on_conflict_do_update(
            index_elements=[User.subject],
            set_={"email": email, "display_name": display_name, "last_seen_at": func.now()},
        )
        .returning(User.id)
    )
    return (await db.execute(stmt)).scalar_one()
