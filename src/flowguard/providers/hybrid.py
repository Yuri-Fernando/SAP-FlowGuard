from typing import Any

from flowguard.domain.models import CapabilityReport
from flowguard.providers.base import SapProvider


class HybridSapProvider(SapProvider):
    """Reads from SAP sandbox and routes all writes to the local mock."""

    name = "hybrid"

    def __init__(self, read_provider: SapProvider, write_provider: SapProvider) -> None:
        self.read_provider = read_provider
        self.write_provider = write_provider

    async def health_check(self) -> bool:
        read_ok = await self.read_provider.health_check()
        write_ok = await self.write_provider.health_check()
        return read_ok and write_ok

    async def discover_capabilities(self) -> CapabilityReport:
        read = await self.read_provider.discover_capabilities()
        write = await self.write_provider.discover_capabilities()
        return CapabilityReport(
            provider=self.name,
            healthy=read.healthy and write.healthy,
            odata_v2=read.odata_v2,
            odata_v4=read.odata_v4,
            sales_order_read=read.sales_order_read,
            sales_order_write=write.sales_order_write,
            purchase_order_read=read.purchase_order_read,
            supplier_invoice_read=read.supplier_invoice_read,
            supplier_invoice_release=write.supplier_invoice_release,
            journal_entry_read=read.journal_entry_read,
            journal_entry_post=write.journal_entry_post,
            csrf=write.csrf,
            etag=write.etag,
            details={"read_provider": read.provider, "write_provider": write.provider},
        )

    async def list_sales_orders(self):
        return await self.read_provider.list_sales_orders()

    async def list_billing_documents(self):
        return await self.read_provider.list_billing_documents()

    async def list_purchase_orders(self):
        return await self.read_provider.list_purchase_orders()

    async def list_supplier_invoices(self):
        return await self.read_provider.list_supplier_invoices()

    async def list_journal_entries(self):
        return await self.read_provider.list_journal_entries()

    async def write(self, action: str, payload: dict[str, Any], etag: str | None = None) -> dict:
        result = await self.write_provider.write(action, payload, etag)
        return {**result, "routed_by": self.name, "target": self.write_provider.name}

    async def close(self) -> None:
        await self.read_provider.close()
        await self.write_provider.close()
