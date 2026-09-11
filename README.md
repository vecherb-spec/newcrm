# LED Ops

Self-hosted ERP/CRM foundation for LED screen engineering, production, installation,
inventory and project finance.

## Included

- CRM pipeline, contacts and omnichannel message persistence
- JWT authentication, first-admin bootstrap and employee roles
- Telegram webhook with secret verification and optional LLM parsing
- deterministic, UI-independent LED screen calculation engine and BOM
- project execution, assignments and stage entities
- SKU stock, reservations/transactions and minimum-stock alerts
- project finance entries, invoices and planned/actual economics endpoint
- escaped Jinja2 commercial proposal preview
- ARQ worker boundary for PDF generation and notifications
- async SQLAlchemy, PostgreSQL, Alembic, Redis and Docker Compose
- responsive dark dashboard shell and OpenAPI UI
- protocol-based banking integration seam for 1C/Russian bank adapters

## Run with Docker

```bash
cp .env.example .env
# Change SECRET_KEY and webhook secrets before exposing the service.
docker compose up --build
```

Open `http://localhost:8000` for the dashboard and `/docs` for the API.
On first launch choose **Первый запуск**, create the administrator, then sign in.
After the first user is created, the bootstrap endpoint closes permanently.

## Local development

Python 3.12+ and PostgreSQL are required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# For local services change postgres/redis hosts in .env to localhost.
alembic upgrade head
uvicorn app.main:app --reload
```

Run quality checks:

```bash
ruff check .
pytest
```

## Architecture

`app/modules` contains domain-oriented modules. The calculator is pure application
logic with no framework or database dependency. External systems live behind adapters
in `app/integrations`; bank implementations can satisfy `BankingGateway` without
changing finance services. API routes use async unit-of-work sessions and never create
database tables at application startup—schema ownership remains with Alembic.

The initial migration is a frozen schema baseline. All later schema changes are applied
as explicit incremental Alembic revisions.

LLM parsing falls back to preserving unparsed source text when no API key is configured.
It must be moved to ARQ before enabling high-volume public webhooks.
