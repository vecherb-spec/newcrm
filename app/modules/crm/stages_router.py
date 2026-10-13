from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.auth.models import User, UserRole
from app.modules.auth.router import CurrentUser
from app.modules.crm.models import LeadPipelineStage
from app.modules.crm.stages_service import (
    ensure_default_pipeline_stages,
    leads_on_stage,
    list_stages_ordered,
)

router = APIRouter(tags=["CRM"])


class PipelineStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    sort_order: int
    is_won: bool
    is_lost: bool
    amo_status_id: int | None = None


class PipelineStageCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=2, max_length=120)
    sort_order: int = Field(default=500, ge=0)
    is_won: bool = False
    is_lost: bool = False
    amo_status_id: int | None = None


class PipelineStageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    is_won: bool | None = None
    is_lost: bool | None = None
    amo_status_id: int | None = None


class PipelineStageReorder(BaseModel):
    codes: list[str] = Field(min_length=1)


async def _require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор")
    return user


@router.get(
    "/leads/stages",
    response_model=list[PipelineStageRead],
    summary="Справочник этапов воронки сделок",
    description=(
        "Возвращает этапы воронки в порядке sort_order (как в amoCRM pipeline 11327590). "
        "Поле `code` используется в `Lead.status` при создании и обновлении сделок."
    ),
)
async def list_pipeline_stages(
    session: AsyncSession = Depends(get_session),
) -> list[LeadPipelineStage]:
    return await list_stages_ordered(session)


@router.post(
    "/leads/stages",
    response_model=PipelineStageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_pipeline_stage(
    payload: PipelineStageCreate,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> LeadPipelineStage:
    await ensure_default_pipeline_stages(session)
    if payload.is_won and payload.is_lost:
        raise HTTPException(status_code=422, detail="Этап не может быть и won, и lost")
    exists = await session.get(LeadPipelineStage, payload.code)
    if exists:
        raise HTTPException(status_code=409, detail="Код этапа уже существует")
    if payload.amo_status_id is not None:
        conflict = await session.scalar(
            select(LeadPipelineStage).where(
                LeadPipelineStage.amo_status_id == payload.amo_status_id
            )
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail="amo_status_id уже привязан к другому этапу",
            )
    stage = LeadPipelineStage(**payload.model_dump())
    session.add(stage)
    await session.commit()
    await session.refresh(stage)
    return stage


@router.patch("/leads/stages/{code}", response_model=PipelineStageRead)
async def update_pipeline_stage(
    code: str,
    payload: PipelineStageUpdate,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> LeadPipelineStage:
    stage = await session.get(LeadPipelineStage, code)
    if stage is None:
        raise HTTPException(status_code=404, detail="Этап не найден")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_won") and updates.get("is_lost"):
        raise HTTPException(status_code=422, detail="Этап не может быть и won, и lost")
    amo_id = updates.get("amo_status_id")
    if amo_id is not None:
        conflict = await session.scalar(
            select(LeadPipelineStage).where(
                LeadPipelineStage.amo_status_id == amo_id,
                LeadPipelineStage.code != code,
            )
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail="amo_status_id уже привязан к другому этапу",
            )
    for field, value in updates.items():
        setattr(stage, field, value)
    await session.commit()
    await session.refresh(stage)
    return stage


@router.put("/leads/stages/reorder", response_model=list[PipelineStageRead])
async def reorder_pipeline_stages(
    payload: PipelineStageReorder,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[LeadPipelineStage]:
    await ensure_default_pipeline_stages(session)
    stages = {
        stage.code: stage
        for stage in await session.scalars(select(LeadPipelineStage))
    }
    missing = [code for code in payload.codes if code not in stages]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестные коды этапов: {', '.join(missing)}",
        )
    for index, code in enumerate(payload.codes):
        stages[code].sort_order = (index + 1) * 10
    await session.commit()
    return await list_stages_ordered(session)


@router.delete("/leads/stages/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline_stage(
    code: str,
    _: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    stage = await session.get(LeadPipelineStage, code)
    if stage is None:
        raise HTTPException(status_code=404, detail="Этап не найден")
    if stage.is_won or stage.is_lost:
        raise HTTPException(status_code=409, detail="Системные этапы won/lost нельзя удалить")
    if await leads_on_stage(session, code) > 0:
        raise HTTPException(status_code=409, detail="На этапе есть сделки")
    await session.delete(stage)
    await session.commit()
