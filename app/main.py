from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.integrations.webhooks import router as webhook_router
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.auth.router import get_current_user
from app.modules.auth.router import router as auth_router
from app.modules.calculator.router import router as calculator_router

# Import models so Alembic sees every table through Base.metadata.
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.crm.router import router as crm_router
from app.modules.documents.router import router as documents_router
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.finance.router import router as finance_router
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.inventory.router import router as inventory_router
from app.modules.projects import models as project_models  # noqa: F401
from app.modules.projects.router import router as projects_router

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="ERP/CRM and operations workspace for LED screen production",
)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

for router in (
    crm_router,
    calculator_router,
    projects_router,
    inventory_router,
    finance_router,
    documents_router,
):
    app.include_router(
        router,
        prefix="/api/v1",
        dependencies=[Depends(get_current_user)],
    )

app.include_router(auth_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html")
