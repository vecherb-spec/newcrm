from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.models import LeadStatus


class LeadCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    source: str = Field(default="manual", max_length=50)
    raw_text: str | None = None
    parsed_data: dict[str, Any] = Field(default_factory=dict)


class LeadUpdate(BaseModel):
    status: LeadStatus


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: LeadStatus
    created_at: datetime
