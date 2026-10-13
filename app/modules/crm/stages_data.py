"""Default amoCRM pipeline 11327590 stages (seed for migrations and runtime)."""

from typing import TypedDict


class StageSeed(TypedDict):
    code: str
    name: str
    sort_order: int
    is_won: bool
    is_lost: bool
    amo_status_id: int


DEFAULT_PIPELINE_STAGES: list[StageSeed] = [
    {
        "code": "UNSORTED",
        "name": "Неразобранное",
        "sort_order": 10,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792562,
    },
    {
        "code": "NEW_LEAD",
        "name": "Новая заявка",
        "sort_order": 20,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792846,
    },
    {
        "code": "QUALIFICATION",
        "name": "Квалификация",
        "sort_order": 30,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792850,
    },
    {
        "code": "PROPOSAL_SENT",
        "name": "КП отправлено",
        "sort_order": 40,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792854,
    },
    {
        "code": "NEGOTIATION",
        "name": "Переговоры",
        "sort_order": 50,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792858,
    },
    {
        "code": "CONTRACT",
        "name": "Договор",
        "sort_order": 60,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792862,
    },
    {
        "code": "PREPAYMENT",
        "name": "Предоплата",
        "sort_order": 70,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792866,
    },
    {
        "code": "PRODUCTION",
        "name": "Производство",
        "sort_order": 80,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792870,
    },
    {
        "code": "DELIVERY",
        "name": "Доставка",
        "sort_order": 90,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792874,
    },
    {
        "code": "INSTALLATION",
        "name": "Монтаж",
        "sort_order": 100,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792878,
    },
    {
        "code": "ACT_SIGNING",
        "name": "Подписание актов",
        "sort_order": 110,
        "is_won": False,
        "is_lost": False,
        "amo_status_id": 88792882,
    },
    {
        "code": "CLOSED_WON",
        "name": "Успешно реализовано",
        "sort_order": 10000,
        "is_won": True,
        "is_lost": False,
        "amo_status_id": 142,
    },
    {
        "code": "CLOSED_LOST",
        "name": "Закрыто и не реализовано",
        "sort_order": 11000,
        "is_won": False,
        "is_lost": True,
        "amo_status_id": 143,
    },
]

LEGACY_STATUS_TO_CODE: dict[str, str] = {
    "NEW": "NEW_LEAD",
    "CALCULATION": "QUALIFICATION",
    "QUALIFICATION": "QUALIFICATION",
    "PROPOSAL_SENT": "PROPOSAL_SENT",
    "NEGOTIATION": "NEGOTIATION",
    "CLOSED_WON": "CLOSED_WON",
    "CLOSED_LOST": "CLOSED_LOST",
}
