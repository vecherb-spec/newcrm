from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.modules.auth.models import User
from app.modules.auth.router import CurrentUser
from app.modules.calculator.models import EngineeringCalculation
from app.modules.crm.models import ActivityType, Contact, Lead, LeadActivity, LeadStatus, LeadTask
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityRead,
    AmoImportDeal,
    AmoImportResult,
    CalculationSummary,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    LeadCreate,
    LeadDetail,
    LeadRead,
    LeadTaskCreate,
    LeadTaskRead,
    LeadTaskUpdate,
    LeadUpdate,
)

router = APIRouter(tags=["CRM"])

STAGE_ALIASES = {
    "новый": LeadStatus.NEW,
    "new": LeadStatus.NEW,
    "квалификация": LeadStatus.QUALIFICATION,
    "qualification": LeadStatus.QUALIFICATION,
    "расчет": LeadStatus.CALCULATION,
    "расчёт": LeadStatus.CALCULATION,
    "calculation": LeadStatus.CALCULATION,
    "calculating": LeadStatus.CALCULATION,
    "кп отправлено": LeadStatus.PROPOSAL_SENT,
    "proposal_sent": LeadStatus.PROPOSAL_SENT,
    "переговоры": LeadStatus.NEGOTIATION,
    "negotiation": LeadStatus.NEGOTIATION,
    "закрыто успешно": LeadStatus.CLOSED_WON,
    "closed_won": LeadStatus.CLOSED_WON,
    "закрыто и не реализовано": LeadStatus.CLOSED_LOST,
    "closed_lost": LeadStatus.CLOSED_LOST,
}

ACTIVITY_ALIASES = {
    "звонок": "CALL",
    "call": "CALL",
    "сообщение": "MESSAGE",
    "message": "MESSAGE",
    "встреча": "MEETING",
    "meeting": "MEETING",
    "комментарий": "COMMENT",
    "comment": "COMMENT",
}


def _lead_options() -> tuple[object, ...]:
    return (
        selectinload(Lead.contact),
        selectinload(Lead.responsible_user),
    )


def _lead_detail_options() -> tuple[object, ...]:
    return (
        *_lead_options(),
        selectinload(Lead.activities).selectinload(LeadActivity.author),
        selectinload(Lead.tasks).selectinload(LeadTask.author),
    )


def _normalize_stage(stage: str) -> LeadStatus:
    try:
        return LeadStatus(stage)
    except ValueError:
        pass
    normalized = stage.strip().casefold()
    if normalized in STAGE_ALIASES:
        return STAGE_ALIASES[normalized]
    raise HTTPException(status_code=422, detail=f"Неизвестная стадия сделки: {stage}")


def _normalize_activity_type(activity_type: str) -> ActivityType:
    try:
        return ActivityType(activity_type)
    except ValueError:
        pass
    normalized = activity_type.strip().casefold()
    try:
        return ActivityType(ACTIVITY_ALIASES.get(normalized, activity_type))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Неизвестный тип заметки: {activity_type}") from error


async def _require_lead(lead_id: UUID, session: AsyncSession) -> Lead:
    lead = await session.scalar(
        select(Lead).where(Lead.id == lead_id).options(*_lead_detail_options())
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    return lead


async def _validate_user(user_id: UUID | None, session: AsyncSession) -> None:
    if user_id and await session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="Ответственный пользователь не найден")


async def _contact_from_payload(
    payload: LeadCreate | LeadUpdate,
    session: AsyncSession,
) -> UUID | None:
    if payload.contact_id:
        if await session.get(Contact, payload.contact_id) is None:
            raise HTTPException(status_code=404, detail="Контакт не найден")
        return payload.contact_id
    if isinstance(payload, LeadUpdate):
        fields = payload.model_fields_set
        has_contact_fields = any(
            field in fields
            for field in ("contact_name", "contact_phone", "contact_email", "contact_company")
        )
    else:
        has_contact_fields = bool(
            payload.contact_name
            or payload.contact_phone
            or payload.contact_email
            or payload.contact_company
        )
    if not has_contact_fields:
        return None
    contact = Contact(
        name=payload.contact_name or payload.title or "Клиент",
        phone=payload.contact_phone,
        email=payload.contact_email,
        company=payload.contact_company,
    )
    session.add(contact)
    await session.flush()
    return contact.id


def _lead_values(payload: LeadCreate | LeadUpdate) -> dict[str, object]:
    excluded = {
        "contact_name",
        "contact_phone",
        "contact_email",
        "contact_company",
    }
    return payload.model_dump(exclude=excluded | {"contact_id"}, exclude_unset=isinstance(payload, LeadUpdate))


async def _lead_detail(lead: Lead, session: AsyncSession) -> LeadDetail:
    calculations = list(
        await session.scalars(
            select(EngineeringCalculation)
            .where(EngineeringCalculation.lead_id == lead.id)
            .order_by(EngineeringCalculation.created_at.desc())
        )
    )
    return LeadDetail.model_validate(
        {
            **LeadRead.model_validate(lead).model_dump(),
            "activities": lead.activities,
            "tasks": lead.tasks,
            "calculations": [
                CalculationSummary.model_validate(calculation) for calculation in calculations
            ],
        }
    )


@router.get("/contacts", response_model=list[ContactRead])
async def list_contacts(
    query: str | None = Query(default=None, min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[Contact]:
    statement = select(Contact).order_by(Contact.created_at.desc())
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(Contact.name.ilike(pattern), Contact.phone.ilike(pattern), Contact.company.ilike(pattern))
        )
    return list(await session.scalars(statement))


@router.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    session: AsyncSession = Depends(get_session),
) -> Contact:
    contact = Contact(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    session: AsyncSession = Depends(get_session),
) -> Contact:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.get("/leads", response_model=list[LeadRead])
async def list_leads(
    stage: LeadStatus | None = None,
    responsible_user_id: UUID | None = None,
    overdue: bool = False,
    query: str | None = Query(default=None, min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[Lead]:
    statement = select(Lead).outerjoin(Contact).options(*_lead_options())
    if stage:
        statement = statement.where(Lead.status == stage)
    if responsible_user_id:
        statement = statement.where(Lead.responsible_user_id == responsible_user_id)
    if overdue:
        statement = statement.where(
            Lead.next_contact_at.is_not(None),
            Lead.next_contact_at < datetime.now(UTC),
            Lead.status.not_in([LeadStatus.CLOSED_WON, LeadStatus.CLOSED_LOST]),
        )
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(Lead.title.ilike(pattern), Contact.phone.ilike(pattern), Contact.company.ilike(pattern))
        )
    result = await session.scalars(statement.order_by(Lead.created_at.desc()))
    return list(result)


@router.post("/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    session: AsyncSession = Depends(get_session),
) -> Lead:
    await _validate_user(payload.responsible_user_id, session)
    contact_id = await _contact_from_payload(payload, session)
    lead = Lead(**_lead_values(payload), contact_id=contact_id)
    session.add(lead)
    await session.commit()
    return await session.scalar(select(Lead).where(Lead.id == lead.id).options(*_lead_options()))


@router.get("/leads/lookup", response_model=list[LeadRead])
async def lookup_leads(
    amo_id: str | None = Query(default=None, min_length=1),
    phone: str | None = Query(default=None, min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[Lead]:
    if not amo_id and not phone:
        raise HTTPException(status_code=422, detail="Укажите amo_id или phone")
    statement = select(Lead).outerjoin(Contact).options(*_lead_options())
    filters = []
    if amo_id:
        filters.append(Lead.amo_id == amo_id)
    if phone:
        filters.append(Contact.phone == phone)
    result = await session.scalars(statement.where(or_(*filters)).order_by(Lead.created_at.desc()))
    return list(result)


@router.get("/leads/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: UUID, session: AsyncSession = Depends(get_session)) -> LeadDetail:
    lead = await _require_lead(lead_id, session)
    return await _lead_detail(lead, session)


@router.patch("/leads/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: UUID, payload: LeadUpdate, session: AsyncSession = Depends(get_session)
) -> Lead:
    lead = await _require_lead(lead_id, session)
    await _validate_user(payload.responsible_user_id, session)
    for field, value in _lead_values(payload).items():
        setattr(lead, field, value)
    if payload.contact_id or any(
        field in payload.model_fields_set
        for field in ("contact_name", "contact_phone", "contact_email", "contact_company")
    ):
        lead.contact_id = await _contact_from_payload(payload, session)
    await session.commit()
    return await session.scalar(select(Lead).where(Lead.id == lead.id).options(*_lead_options()))


@router.post(
    "/leads/{lead_id}/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    lead_id: UUID,
    payload: ActivityCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LeadActivity:
    await _require_lead(lead_id, session)
    activity = LeadActivity(
        lead_id=lead_id,
        type=payload.type,
        body=payload.body,
        author_id=actor.id,
        **({"occurred_at": payload.occurred_at} if payload.occurred_at else {}),
    )
    session.add(activity)
    await session.commit()
    return await session.scalar(
        select(LeadActivity)
        .where(LeadActivity.id == activity.id)
        .options(selectinload(LeadActivity.author))
    )


@router.post(
    "/leads/{lead_id}/tasks",
    response_model=LeadTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    lead_id: UUID,
    payload: LeadTaskCreate,
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LeadTask:
    await _require_lead(lead_id, session)
    task = LeadTask(lead_id=lead_id, author_id=actor.id, **payload.model_dump())
    session.add(task)
    await session.commit()
    return await session.scalar(
        select(LeadTask).where(LeadTask.id == task.id).options(selectinload(LeadTask.author))
    )


@router.patch("/leads/{lead_id}/tasks/{task_id}", response_model=LeadTaskRead)
async def update_task(
    lead_id: UUID,
    task_id: UUID,
    payload: LeadTaskUpdate,
    session: AsyncSession = Depends(get_session),
) -> LeadTask:
    task = await session.scalar(
        select(LeadTask)
        .where(LeadTask.id == task_id, LeadTask.lead_id == lead_id)
        .options(selectinload(LeadTask.author))
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    updates = payload.model_dump(exclude_unset=True)
    if "is_completed" in updates:
        task.completed_at = datetime.now(UTC) if updates["is_completed"] else None
    for field, value in updates.items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/imports/amo/deals", response_model=AmoImportResult)
async def import_amo_deals(
    payload: list[AmoImportDeal],
    actor: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> AmoImportResult:
    created = 0
    updated = 0
    notes_created = 0
    lead_ids: list[UUID] = []

    for item in payload:
        contact = None
        if item.contact.phone:
            contact = await session.scalar(select(Contact).where(Contact.phone == item.contact.phone))
        if contact is None and item.contact.email:
            contact = await session.scalar(select(Contact).where(Contact.email == item.contact.email))
        if contact is None:
            contact = Contact(**item.contact.model_dump())
            session.add(contact)
            await session.flush()
        else:
            for field, value in item.contact.model_dump(exclude_unset=True).items():
                setattr(contact, field, value)

        lead = await session.scalar(
            select(Lead).where(Lead.amo_id == item.amo_id).options(*_lead_detail_options())
        )
        lead_values = {
            "amo_id": item.amo_id,
            "title": item.title,
            "status": _normalize_stage(item.stage),
            "amount": item.amount,
            "source": item.source,
            "contact_id": contact.id,
        }
        if lead is None:
            lead = Lead(**lead_values)
            if item.created_at:
                lead.created_at = item.created_at
            session.add(lead)
            await session.flush()
            created += 1
        else:
            for field, value in lead_values.items():
                setattr(lead, field, value)
            updated += 1

        for note in item.notes:
            note_type = _normalize_activity_type(note.type)
            body = f"{note.author}: {note.text}" if note.author else note.text
            duplicate_query = select(LeadActivity.id).where(
                LeadActivity.lead_id == lead.id,
                LeadActivity.type == note_type,
                LeadActivity.body == body,
            )
            if note.created_at:
                duplicate_query = duplicate_query.where(LeadActivity.occurred_at == note.created_at)
            duplicate = await session.scalar(duplicate_query)
            if duplicate:
                continue
            session.add(
                LeadActivity(
                    lead_id=lead.id,
                    type=note_type,
                    body=body,
                    author_id=actor.id,
                    **({"occurred_at": note.created_at} if note.created_at else {}),
                )
            )
            notes_created += 1
        lead_ids.append(lead.id)

    await session.commit()
    return AmoImportResult(
        created=created,
        updated=updated,
        notes_created=notes_created,
        lead_ids=lead_ids,
    )
