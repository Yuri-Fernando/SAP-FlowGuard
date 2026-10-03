from typing import Any

from flowguard.domain.models import CapabilityReport
from flowguard.providers.base import SapProvider, SapWriteError
from flowguard.providers.http import ODataHttpClient
from flowguard.providers.mappers import (
    billing_document,
    journal_entry,
    purchase_order,
    sales_order,
    supplier_invoice,
)


class MockSapProvider(SapProvider):
    name = "mock"

    def __init__(self, base_url: str, timeout: float = 15) -> None:
        self.http = ODataHttpClient(base_url, timeout=timeout)

    async def health_check(self) -> bool:
        return await self.http.health()

    async def discover_capabilities(self) -> CapabilityReport:
        healthy = await self.health_check()
        return CapabilityReport(
            provider=self.name,
            healthy=healthy,
            odata_v2=True,
            odata_v4=True,
            sales_order_read=True,
            sales_order_write=True,
            purchase_order_read=True,
            supplier_invoice_read=True,
            supplier_invoice_release=True,
            journal_entry_read=True,
            journal_entry_post=True,
            csrf=True,
            etag=True,
        )

    async def list_sales_orders(self):
        rows = await self.http.get_collection(
            "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder", {"$top": 100}
        )
        return [sales_order(row) for row in rows]

    async def list_billing_documents(self):
        rows = await self.http.get_collection(
            "/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV/A_BillingDocument", {"$top": 100}
        )
        return [billing_document(row) for row in rows]

    async def list_purchase_orders(self):
        rows = await self.http.get_collection(
            "/sap/opu/odata4/sap/api_purchaseorder_2/srvd_a2x/sap/purchaseorder/0001/PurchaseOrder",
            {"$top": 100},
        )
        return [purchase_order(row) for row in rows]

    async def list_supplier_invoices(self):
        rows = await self.http.get_collection(
            "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV_0001/A_SupplierInvoice",
            {"$top": 100},
        )
        return [supplier_invoice(row) for row in rows]

    async def list_journal_entries(self):
        rows = await self.http.get_collection("/mock/fi/journal-entries", {"$top": 100})
        return [journal_entry(row) for row in rows]

    async def write(self, action: str, payload: dict[str, Any], etag: str | None = None) -> dict:
        token_response = await self.http.client.get("/mock/csrf", headers={"x-csrf-token": "fetch"})
        token_response.raise_for_status()
        token = token_response.headers.get("x-csrf-token")
        headers = {"x-csrf-token": token or "", "if-match": etag or "*"}
        response = await self.http.client.post(
            f"/mock/actions/{action}", json=payload, headers=headers
        )
        if response.is_error:
            raise SapWriteError(f"Mock action {action} failed with HTTP {response.status_code}")
        return response.json()

    async def close(self) -> None:
        await self.http.close()
