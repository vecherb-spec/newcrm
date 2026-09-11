from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.modules.documents.service import render_document

router = APIRouter(prefix="/documents", tags=["Documents"])


class QuotePreview(BaseModel):
    number: str
    customer: str
    project: str
    total: float = Field(ge=0)
    currency: str = "RUB"


@router.post("/quote/preview", response_class=HTMLResponse)
async def preview_quote(payload: QuotePreview) -> str:
    return render_document("quote.html", payload.model_dump())
