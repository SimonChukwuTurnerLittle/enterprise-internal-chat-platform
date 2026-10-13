import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.chunking import Section, TextChunk, chunk_sections, split_markdown
from app.modules.knowledge.models import Chunk, Document, KnowledgeSource
from app.modules.llm.embeddings import Embedder

CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


class UnsupportedDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class IngestResult:
    document: Document
    status: Literal["created", "updated", "unchanged"]


def extract_sections(filename: str, data: bytes) -> list[Section]:
    extension = Path(filename).suffix.lower()
    if extension not in CONTENT_TYPES:
        raise UnsupportedDocumentError(
            f"Unsupported file type '{extension}'. Use one of: {', '.join(CONTENT_TYPES)}"
        )
    if extension == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            return [
                Section(f"Page {number}", text)
                for number, page in enumerate(reader.pages, start=1)
                if (text := (page.extract_text() or "").strip())
            ]
        except PdfReadError as exc:
            raise UnsupportedDocumentError("The PDF could not be read") from exc
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Text files must be UTF-8 encoded") from exc
    return split_markdown(text)


def derive_title(filename: str, sections: list[Section]) -> str:
    if sections and sections[0].heading:
        return sections[0].heading.split(" > ")[0]
    return Path(filename).stem.replace("-", " ").replace("_", " ").strip().title()


def embedding_text(document_title: str, chunk: TextChunk) -> str:
    """Prefix the title and heading so short chunks still carry their topic."""
    heading = f"{chunk.heading}\n" if chunk.heading else ""
    return f"{document_title}\n{heading}\n{chunk.content}"


async def ingest_document(
    db: AsyncSession,
    embedder: Embedder,
    *,
    source: KnowledgeSource,
    filename: str,
    data: bytes,
    title: str | None = None,
    uri: str | None = None,
    uploaded_by: str | None = None,
) -> IngestResult:
    """Parse, chunk, embed and store a document. Re-ingesting the same title replaces its
    chunks; an unchanged file (same checksum) is skipped. Caller commits."""
    sections = extract_sections(filename, data)
    chunks = chunk_sections(sections)
    if not chunks:
        raise UnsupportedDocumentError("No text could be extracted from the document")
    title = (title or derive_title(filename, sections)).strip()[:300]
    checksum = hashlib.sha256(data).hexdigest()

    existing = await db.scalar(
        select(Document).where(Document.source_id == source.id, Document.title == title)
    )
    if existing is not None and existing.checksum == checksum:
        return IngestResult(existing, "unchanged")

    vectors = await embedder.embed_documents([embedding_text(title, c) for c in chunks])

    if existing is not None:
        await db.execute(delete(Chunk).where(Chunk.document_id == existing.id))
        document = existing
        status: Literal["created", "updated"] = "updated"
    else:
        document = Document(source_id=source.id, title=title)
        db.add(document)
        status = "created"
    document.uri = uri
    document.content_type = CONTENT_TYPES[Path(filename).suffix.lower()]
    document.checksum = checksum
    document.chunk_count = len(chunks)
    document.uploaded_by = uploaded_by
    await db.flush()

    db.add_all(
        Chunk(
            document_id=document.id,
            ordinal=chunk.ordinal,
            heading=chunk.heading[:500] if chunk.heading else None,
            content=chunk.content,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )
    await db.flush()
    return IngestResult(document, status)
