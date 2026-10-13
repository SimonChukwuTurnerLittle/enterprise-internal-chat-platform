from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Application(Base):
    """A business application known to the platform.

    M1 uses it for widget embedding (allowed origins) and for app-specific knowledge.
    M2 adds connector configuration and tools.
    """

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, e.g. "hr-portal"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Origins allowed to embed the chat widget, e.g. ["https://hr.example.com"].
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
