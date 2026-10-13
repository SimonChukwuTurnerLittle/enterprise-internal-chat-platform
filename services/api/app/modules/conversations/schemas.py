import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    origin_app_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    origin_app_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class Citation(BaseModel):
    n: int
    document_id: uuid.UUID
    document_title: str
    source_name: str
    heading: str | None
    uri: str | None
    snippet: str
    score: float


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[Citation]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class RecordRef(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    id: str = Field(min_length=1, max_length=100)


class HostContext(BaseModel):
    """Where the user is in the host application. Supplied by the browser, so it is an
    unverified hint: it may steer retrieval, never authorisation (signed context arrives in M2)."""

    app_id: str | None = Field(default=None, max_length=64)
    page: str | None = Field(default=None, max_length=500)
    module: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    record: RecordRef | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    context: HostContext | None = None
