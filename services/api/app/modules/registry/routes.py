from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.identity.deps import get_principal
from app.modules.identity.principal import Principal
from app.modules.registry.models import Application

router = APIRouter(prefix="/api/v1", tags=["applications"])


class ApplicationOut(BaseModel):
    id: str
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class WidgetConfigOut(BaseModel):
    app_id: str
    name: str
    allowed_origins: list[str]


@router.get("/applications", response_model=list[ApplicationOut])
async def list_applications(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(get_principal)
) -> list[Application]:
    stmt = select(Application).where(Application.enabled.is_(True)).order_by(Application.name)
    return list((await db.scalars(stmt)).all())


@router.get("/widget/config", response_model=WidgetConfigOut)
async def widget_config(
    app_id: str = Query(min_length=1, max_length=64), db: AsyncSession = Depends(get_db)
) -> WidgetConfigOut:
    """Public: lets the embedded widget verify which host origins may talk to it."""
    app = await db.get(Application, app_id)
    if app is None or not app.enabled:
        raise HTTPException(status_code=404, detail="Unknown application")
    return WidgetConfigOut(app_id=app.id, name=app.name, allowed_origins=app.allowed_origins)
