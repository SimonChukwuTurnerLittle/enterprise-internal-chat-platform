import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.modules.audit.service import record_audit
from app.modules.identity.deps import require_admin
from app.modules.identity.principal import Principal
from app.modules.knowledge.ingest import UnsupportedDocumentError, ingest_document
from app.modules.knowledge.models import Document, KnowledgeSource
from app.modules.llm.embeddings import Embedder
from app.modules.llm.factory import get_embedder
from app.modules.registry.models import Application

router = APIRouter(prefix="/api/v1/admin/knowledge", tags=["admin"])

RoleName = Annotated[
    str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
]


class SourceCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    application_id: str | None = Field(default=None, max_length=64)
    acl_roles: list[RoleName] = Field(default_factory=list, max_length=20)


class SourceOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    application_id: str | None
    acl_roles: list[str]
    document_count: int


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    uri: str | None
    content_type: str
    chunk_count: int
    uploaded_by: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResult(BaseModel):
    status: str
    document: DocumentOut


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require_admin)
) -> list[SourceOut]:
    counts = (
        select(Document.source_id, func.count(Document.id).label("n"))
        .group_by(Document.source_id)
        .subquery()
    )
    stmt = (
        select(KnowledgeSource, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.source_id == KnowledgeSource.id)
        .order_by(KnowledgeSource.name)
    )
    return [
        SourceOut(
            id=source.id,
            slug=source.slug,
            name=source.name,
            description=source.description,
            application_id=source.application_id,
            acl_roles=source.acl_roles,
            document_count=count,
        )
        for source, count in (await db.execute(stmt)).all()
    ]


@router.post("/sources", response_model=SourceOut, status_code=201)
async def create_source(
    body: SourceCreate,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_admin),
) -> SourceOut:
    if await db.scalar(select(KnowledgeSource.id).where(KnowledgeSource.slug == body.slug)):
        raise HTTPException(status_code=409, detail="A source with this slug already exists")
    if body.application_id and await db.get(Application, body.application_id) is None:
        raise HTTPException(status_code=422, detail="Unknown application")
    source = KnowledgeSource(**body.model_dump())
    db.add(source)
    await db.flush()
    record_audit(
        db,
        action="knowledge.source.create",
        principal=principal,
        resource_type="knowledge_source",
        resource_id=str(source.id),
        details={"slug": source.slug, "acl_roles": source.acl_roles},
    )
    await db.commit()
    return SourceOut(**body.model_dump(), id=source.id, document_count=0)


@router.get("/sources/{source_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require_admin),
) -> list[Document]:
    stmt = select(Document).where(Document.source_id == source_id).order_by(Document.title)
    return list((await db.scalars(stmt)).all())


@router.post("/sources/{source_id}/documents", response_model=UploadResult, status_code=201)
async def upload_document(
    source_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=300),
    uri: str | None = Form(default=None, max_length=1000),
    db: AsyncSession = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require_admin),
) -> UploadResult:
    source = await db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if uri and not uri.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="uri must be an http(s) URL")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    try:
        result = await ingest_document(
            db,
            embedder,
            source=source,
            filename=file.filename or "upload.txt",
            data=data,
            title=title,
            uri=uri,
            uploaded_by=principal.subject,
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit(
        db,
        action="knowledge.document.upload",
        principal=principal,
        resource_type="document",
        resource_id=str(result.document.id),
        details={"source": source.slug, "title": result.document.title, "status": result.status},
    )
    await db.commit()
    await db.refresh(result.document)  # load server-generated timestamps
    return UploadResult(status=result.status, document=DocumentOut.model_validate(result.document))


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_admin),
) -> Response:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(document)
    record_audit(
        db,
        action="knowledge.document.delete",
        principal=principal,
        resource_type="document",
        resource_id=str(document_id),
        details={"title": document.title},
    )
    await db.commit()
    return Response(status_code=204)
