from abc import ABC, abstractmethod
from typing import Any

from flowguard.domain.models import (
    BillingDocument,
    CapabilityReport,
    JournalEntry,
    PurchaseOrder,
    SalesOrder,
    SupplierInvoice,
)


class SapProviderError(RuntimeError):
    """Base provider failure."""


class SapWriteError(SapProviderError):
    """A protected SAP write could not be completed."""


class SapProvider(ABC):
    name: str

    @abstractmethod
    async def health_check(self) -> bool: ...

    @abstractmethod
    async def discover_capabilities(self) -> CapabilityReport: ...

    @abstractmethod
    async def list_sales_orders(self) -> list[SalesOrder]: ...

    @abstractmethod
    async def list_billing_documents(self) -> list[BillingDocument]: ...

    @abstractmethod
    async def list_purchase_orders(self) -> list[PurchaseOrder]: ...

    @abstractmethod
    async def list_supplier_invoices(self) -> list[SupplierInvoice]: ...

    @abstractmethod
    async def list_journal_entries(self) -> list[JournalEntry]: ...

    async def write(self, action: str, payload: dict[str, Any], etag: str | None = None) -> dict:
        raise SapWriteError(f"Provider {self.name} does not support action {action}")

    async def close(self) -> None:
        return None
