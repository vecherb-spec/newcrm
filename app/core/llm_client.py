import json
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import Settings


class ParsedLead(BaseModel):
    width_m: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)
    pitch_mm: float | None = Field(default=None, gt=0)
    environment: str | None = None
    location: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    notes: str | None = None


class LeadParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def parse(self, text: str) -> ParsedLead:
        if not self.settings.llm_api_key:
            return ParsedLead(notes=text)
        client = AsyncOpenAI(
            api_key=self.settings.llm_api_key.get_secret_value(),
            base_url=self.settings.llm_base_url,
        )
        response = await client.chat.completions.create(
            model=self.settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract an LED screen sales lead. Return JSON with width_m, height_m, "
                        "pitch_mm, environment, location, contact_name, contact_phone, notes. "
                        "Use null for unknown values; do not invent facts."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        raw: Any = json.loads(response.choices[0].message.content or "{}")
        return ParsedLead.model_validate(raw)
