from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Lead, LeadPipelineStage
from app.modules.crm.stages_data import DEFAULT_PIPELINE_STAGES


async def ensure_default_pipeline_stages(session: AsyncSession) -> None:
    count = await session.scalar(select(func.count()).select_from(LeadPipelineStage))
    if count:
        return
    for row in DEFAULT_PIPELINE_STAGES:
        session.add(LeadPipelineStage(**row))
    await session.flush()


async def list_stages_ordered(session: AsyncSession) -> list[LeadPipelineStage]:
    await ensure_default_pipeline_stages(session)
    return list(
        await session.scalars(
            select(LeadPipelineStage).order_by(LeadPipelineStage.sort_order.asc())
        )
    )


async def stage_codes_terminal(session: AsyncSession) -> list[str]:
    await ensure_default_pipeline_stages(session)
    rows = await session.scalars(
        select(LeadPipelineStage.code).where(
            (LeadPipelineStage.is_won.is_(True)) | (LeadPipelineStage.is_lost.is_(True))
        )
    )
    return list(rows)


async def resolve_stage_code(
    session: AsyncSession,
    *,
    amo_status_id: int | None = None,
    stage: str | None = None,
) -> tuple[str, bool]:
    """Return (stage_code, empty_stage_mapped)."""
    await ensure_default_pipeline_stages(session)
    if amo_status_id is not None:
        found = await session.scalar(
            select(LeadPipelineStage.code).where(
                LeadPipelineStage.amo_status_id == amo_status_id
            )
        )
        if found:
            return found, False
    if not stage or not str(stage).strip():
        return "QUALIFICATION", True

    raw = str(stage).strip()
    by_code = await session.scalar(
        select(LeadPipelineStage.code).where(LeadPipelineStage.code == raw)
    )
    if by_code:
        return by_code, False

    normalized = raw.casefold()
    stages = await list_stages_ordered(session)
    for item in stages:
        if item.name.casefold() == normalized:
            return item.code, False

    from app.modules.crm.stage_aliases import STAGE_ALIASES

    alias = STAGE_ALIASES.get(normalized)
    if alias:
        return alias, False

    raise ValueError(f"Неизвестная стадия сделки: {stage}")


async def validate_stage_code(session: AsyncSession, code: str) -> str:
    await ensure_default_pipeline_stages(session)
    exists = await session.scalar(
        select(LeadPipelineStage.code).where(LeadPipelineStage.code == code)
    )
    if not exists:
        raise ValueError(f"Неизвестный код этапа: {code}")
    return code


async def leads_on_stage(session: AsyncSession, code: str) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Lead).where(Lead.status == code))
        or 0
    )
