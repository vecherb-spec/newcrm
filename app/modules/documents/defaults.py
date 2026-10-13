from app.modules.documents.models import DocumentTemplate, DocumentType

DEFAULT_TEMPLATES: list[tuple[DocumentType, str, str]] = [
    (
        DocumentType.QUOTE,
        "Коммерческое предложение",
        """
<h1>Коммерческое предложение {{ number }}</h1>
{{ letterhead_html|safe }}
<p>Заказчик: {{ customer.company or customer.name }}</p>
<p>Проект: {{ project.name or lead.title }}</p>
<p>Сумма: {{ amount }} {{ currency }} ({{ amount_words }})</p>
<p>НДС: {{ vat_rate }}% {% if vat_included %}включён{% else %}сверху{% endif %}</p>
        """,
    ),
    (
        DocumentType.INVOICE,
        "Счёт на оплату",
        """
<h1>Счёт {{ number }} от {{ issued_on }}</h1>
<p>Поставщик: {{ supplier.name }}, ИНН {{ supplier.inn }}</p>
<p>Покупатель: {{ customer.company or customer.name }}, ИНН {{ customer.inn or '—' }}</p>
<p>К оплате: {{ amount }} {{ currency }} ({{ amount_words }})</p>
<p>НДС {{ vat_rate }}%: {{ vat_amount }}</p>
        """,
    ),
    (
        DocumentType.SUPPLY_CONTRACT,
        "Договор поставки",
        """
<h1>Договор поставки {{ number }}</h1>
<p>Поставщик: {{ supplier.name }}</p>
<p>Покупатель: {{ customer.company or customer.name }}</p>
<p>Предмет: LED-экран, проект {{ project.name or lead.title }}</p>
<p>Стоимость: {{ amount }} ({{ amount_words }})</p>
        """,
    ),
    (
        DocumentType.WAYBILL_UPD,
        "ТОРГ-12 / УПД",
        """
<h1>УПД {{ number }}</h1>
<p>Грузоотправитель: {{ supplier.name }}</p>
<p>Грузополучатель: {{ customer.company or customer.name }}</p>
<p>Сумма: {{ amount }}</p>
        """,
    ),
    (
        DocumentType.ACT,
        "Акт выполненных работ",
        """
<h1>Акт {{ number }}</h1>
<p>Исполнитель: {{ supplier.name }}</p>
<p>Заказчик: {{ customer.company or customer.name }}</p>
<p>Объект: {{ project.installation_address or project.name }}</p>
<p>Стоимость работ: {{ amount }} ({{ amount_words }})</p>
        """,
    ),
    (
        DocumentType.SPECIFICATION,
        "Спецификация",
        """
<h1>Спецификация {{ number }}</h1>
<p>Проект: {{ project.name or lead.title }}</p>
<pre>{{ calculation.result }}</pre>
        """,
    ),
]


async def ensure_default_templates(session) -> None:
    from sqlalchemy import select

    existing = await session.scalar(select(DocumentTemplate.id).limit(1))
    if existing:
        return
    for doc_type, name, body in DEFAULT_TEMPLATES:
        session.add(DocumentTemplate(doc_type=doc_type, name=name, body_html=body.strip()))
    await session.flush()
