from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.models import ActivityType, LeadStatus, TaskPriority, TaskStatus


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


class ContactCreate(BaseModel):
    amo_id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    normalized_phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    ogrn: str | None = Field(default=None, max_length=15)
    legal_address: str | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=9)
    bank_account: str | None = Field(default=None, max_length=34)
    bank_corr_account: str | None = Field(default=None, max_length=34)
    telegram: str | None = Field(default=None, max_length=160)
    vk: str | None = Field(default=None, max_length=160)
    radist_chat_id: str | None = Field(default=None, max_length=80)


class ContactUpdate(BaseModel):
    amo_id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    normalized_phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    ogrn: str | None = Field(default=None, max_length=15)
    legal_address: str | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=9)
    bank_account: str | None = Field(default=None, max_length=34)
    bank_corr_account: str | None = Field(default=None, max_length=34)
    telegram: str | None = Field(default=None, max_length=160)
    vk: str | None = Field(default=None, max_length=160)
    radist_chat_id: str | None = Field(default=None, max_length=80)


class ContactRead(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class LeadCreate(BaseModel):
    amo_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=2, max_length=255)
    status: LeadStatus = Field(
        default=LeadStatus.NEW_LEAD,
        description="Код этапа воронки. Справочник: GET /api/v1/leads/stages",
    )
    source: str = Field(default="manual", max_length=50)
    raw_text: str | None = None
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    contact_id: UUID | None = None
    contact_name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_company: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    responsible_user_id: UUID | None = None
    next_contact_at: datetime | None = None
    lost_reason: str | None = None
    contract_signed: bool = False
    paid: bool = False


class LeadUpdate(BaseModel):
    amo_id: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    status: LeadStatus | None = Field(
        default=None,
        description="Код этапа воронки. Справочник: GET /api/v1/leads/stages",
    )
    source: str | None = Field(default=None, max_length=50)
    raw_text: str | None = None
    parsed_data: dict[str, Any] | None = None
    contact_id: UUID | None = None
    contact_name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_company: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    responsible_user_id: UUID | None = None
    next_contact_at: datetime | None = None
    lost_reason: str | None = None
    contract_signed: bool | None = None
    paid: bool | None = None


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: LeadStatus
    contact: ContactRead | None = None
    responsible_user: UserSummary | None = None
    created_at: datetime


class ActivityCreate(BaseModel):
    type: ActivityType
    body: str = Field(min_length=1)
    occurred_at: datetime | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    type: ActivityType
    body: str
    author_id: UUID
    author: UserSummary | None = None
    occurred_at: datetime
    created_at: datetime


class LeadTaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    due_at: datetime | None = None
    responsible_user_id: UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL


class LeadTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    due_at: datetime | None = None
    responsible_user_id: UUID | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    is_completed: bool | None = None


class LeadTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID | None
    contact_id: UUID | None
    title: str
    due_at: datetime | None
    status: TaskStatus
    priority: TaskPriority
    is_completed: bool
    completed_at: datetime | None
    responsible_user_id: UUID | None
    responsible_user: UserSummary | None = None
    author_id: UUID
    author: UserSummary | None = None
    kind: str
    created_at: datetime


class CalculationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    total_bom_cost: Decimal
    suggested_sales_price: Decimal
    created_at: datetime


class LeadDetail(LeadRead):
    activities: list[ActivityRead] = Field(default_factory=list)
    tasks: list[LeadTaskRead] = Field(default_factory=list)
    calculations: list[CalculationSummary] = Field(default_factory=list)
    project_id: UUID | None = None
    ready_for_project: bool = False


class AmoImportContact(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    kpp: str | None = Field(default=None, max_length=9)
    ogrn: str | None = Field(default=None, max_length=15)
    legal_address: str | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_bik: str | None = Field(default=None, max_length=9)
    bank_account: str | None = Field(default=None, max_length=34)
    bank_corr_account: str | None = Field(default=None, max_length=34)
    telegram: str | None = Field(default=None, max_length=160)
    vk: str | None = Field(default=None, max_length=160)
    radist_chat_id: str | int | None = None


class AmoImportNote(BaseModel):
    type: str = ActivityType.COMMENT.value
    text: str = Field(min_length=1)
    created_at: datetime | None = None
    author: str | None = Field(default=None, max_length=160)


class AmoImportDeal(BaseModel):
    amo_id: str | int | None = None
    title: str = Field(min_length=2, max_length=255)
    stage: str | None = Field(
        default=None,
        description="Название или код этапа; приоритет у amo_status_id",
    )
    amo_status_id: int | None = Field(
        default=None,
        description="ID статуса amoCRM (pipeline 11327590); маппится через lead_pipeline_stages",
    )
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    source: str | None = Field(default="amoCRM", max_length=50)
    created_at: datetime | None = None
    contact: AmoImportContact
    notes: list[AmoImportNote] = Field(default_factory=list)


class AmoImportResult(BaseModel):
    created: int
    updated: int
    notes_created: int
    empty_stage_flagged: int = 0
    dry_run: bool = False
    lead_ids: list[UUID]
