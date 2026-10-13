"""Imports every ORM model so Base.metadata is complete (used by Alembic and tests)."""

from app.core.db import Base
from app.modules.audit.models import AuditEvent
from app.modules.conversations.models import Conversation, Message
from app.modules.identity.models import User
from app.modules.knowledge.models import Chunk, Document, KnowledgeSource
from app.modules.registry.models import Application

__all__ = [
    "Application",
    "AuditEvent",
    "Base",
    "Chunk",
    "Conversation",
    "Document",
    "KnowledgeSource",
    "Message",
    "User",
]
