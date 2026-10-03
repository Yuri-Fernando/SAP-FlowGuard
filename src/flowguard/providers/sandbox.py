from flowguard.domain.models import CapabilityReport
from flowguard.providers.base import SapProvider
from flowguard.providers.http import ODataHttpClient
from flowguard.providers.mappers import (
    billing_document,
    purchase_order,
    sales_order,
    supplier_invoice,
)


class SapSandboxProvider(SapProvider):
    """Read-only SAP Business Accelerator Hub provider."""

    name = "sap-sandbox"

    def __init__(self, base_url: str, api_key: str, timeout: float = 15) -> None:
        self.http = ODataHttpClient(
            base_url, headers={"APIKey": api_key, "Accept": "application/json"}, timeout=timeout
        )

    async def health_check(self) -> bool:
        try:
            await self.http.get_collection(
                "/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder", {"$top": 1}
            )
            return True
        except Exception:
            return False

    async def discover_capabilities(self) -> CapabilityReport:
        healthy = await self.health_check()
        return CapabilityReport(
            provider=self.name,
            healthy=healthy,
            odata_v2=True,
            odata_v4=True,
            sales_order_read=healthy,
            purchase_order_read=healthy,
            supplier_invoice_read=healthy,
            details={"write_policy": "read-only", "source": "SAP Business Accelerator Hub"},
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
        return []

    async def close(self) -> None:
        await self.http.close()
