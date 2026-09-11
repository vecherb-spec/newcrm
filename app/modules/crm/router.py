from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.crm.models import Lead
from app.modules.crm.schemas import LeadCreate, LeadRead, LeadUpdate

router = APIRouter(prefix="/leads", tags=["CRM"])


@router.get("", response_model=list[LeadRead])
async def list_leads(session: AsyncSession = Depends(get_session)) -> list[Lead]:
    result = await session.scalars(select(Lead).order_by(Lead.created_at.desc()))
    return list(result)


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadCreate, session: AsyncSession = Depends(get_session)) -> Lead:
    lead = Lead(**payload.model_dump())
    session.add(lead)
    await session.commit()
    await session.refresh(lead)
    return lead


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: UUID, payload: LeadUpdate, session: AsyncSession = Depends(get_session)
) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = payload.status
    await session.commit()
    await session.refresh(lead)
    return lead
