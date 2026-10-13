"""Operational commands.

    uv run python -m app.cli seed --path ../../knowledge-seed

`seed` reads <path>/manifest.yaml, upserts applications and knowledge sources, and ingests
the listed documents. It is idempotent: unchanged documents are skipped.
"""

import argparse
import asyncio
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine, get_sessionmaker
from app.modules.audit.service import record_audit
from app.modules.knowledge.ingest import ingest_document
from app.modules.knowledge.models import KnowledgeSource
from app.modules.llm.factory import get_embedder
from app.modules.registry.models import Application


async def _upsert_application(db: AsyncSession, spec: dict[str, Any]) -> None:
    app = await db.get(Application, spec["id"])
    if app is None:
        app = Application(id=spec["id"])
        db.add(app)
    app.name = spec["name"]
    app.description = spec.get("description")
    app.allowed_origins = list(spec.get("allowed_origins", []))
    app.enabled = bool(spec.get("enabled", True))


async def _upsert_source(db: AsyncSession, spec: dict[str, Any]) -> KnowledgeSource:
    source = await db.scalar(select(KnowledgeSource).where(KnowledgeSource.slug == spec["slug"]))
    if source is None:
        source = KnowledgeSource(slug=spec["slug"])
        db.add(source)
    source.name = spec["name"]
    source.description = spec.get("description")
    source.application_id = spec.get("application_id")
    source.acl_roles = list(spec.get("acl_roles", []))
    await db.flush()
    return source


async def seed(path: Path) -> None:
    manifest = yaml.safe_load((path / "manifest.yaml").read_text(encoding="utf-8"))
    embedder = get_embedder()
    async with get_sessionmaker()() as db:
        for spec in manifest.get("applications", []):
            await _upsert_application(db, spec)
        await db.flush()
        for spec in manifest.get("sources", []):
            source = await _upsert_source(db, spec)
            for doc in spec.get("documents", []):
                file_path = path / doc["file"]
                result = await ingest_document(
                    db,
                    embedder,
                    source=source,
                    filename=file_path.name,
                    data=file_path.read_bytes(),
                    title=doc.get("title"),
                    uri=doc.get("uri"),
                    uploaded_by="seed",
                )
                print(f"  [{result.status:9}] {source.slug}: {result.document.title}")
        record_audit(db, action="knowledge.seed", actor_subject="system:cli")
        await db.commit()
    await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_cmd = commands.add_parser("seed", help="Load applications and knowledge from a manifest")
    seed_cmd.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(seed(args.path))


if __name__ == "__main__":
    main()
