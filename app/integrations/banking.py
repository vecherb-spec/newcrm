from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class BankTransaction:
    external_id: str
    occurred_on: date
    amount: Decimal
    purpose: str
    counterparty: str


class BankingGateway(Protocol):
    async def fetch_transactions(self, since: date) -> list[BankTransaction]: ...

    async def get_invoice_payment_status(self, invoice_number: str) -> str: ...


class NotConfiguredBankingGateway:
    async def fetch_transactions(self, since: date) -> list[BankTransaction]:
        raise RuntimeError("Banking integration is not configured")

    async def get_invoice_payment_status(self, invoice_number: str) -> str:
        raise RuntimeError("Banking integration is not configured")
