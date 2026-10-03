from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from flowguard.domain.models import (
    BillingDocument,
    ExceptionRecord,
    JournalEntry,
    Module,
    PurchaseOrder,
    SalesOrder,
    Severity,
    SupplierInvoice,
)

UTC = timezone.utc


class RulesEngine:
    """Deterministic FI/SD/MM rules. AI is deliberately excluded from decisions."""

    def __init__(
        self,
        *,
        invoice_tolerance_percent: Decimal = Decimal("2"),
        critical_amount: Decimal = Decimal("100000"),
        blocked_invoice_sla_days: int = 3,
    ) -> None:
        self.invoice_tolerance_percent = invoice_tolerance_percent
        self.critical_amount = critical_amount
        self.blocked_invoice_sla_days = blocked_invoice_sla_days

    def o2c(
        self,
        sales_orders: list[SalesOrder],
        billings: list[BillingDocument],
        correlation_id: UUID,
    ) -> list[ExceptionRecord]:
        exceptions: list[ExceptionRecord] = []
        orders = {order.document_id: order for order in sales_orders}
        billed_orders = {billing.sales_order_id for billing in billings if billing.sales_order_id}

        for order in sales_orders:
            if order.document_id not in billed_orders:
                exceptions.append(
                    self._exception(
                        "SD001",
                        Module.SD,
                        "O2C",
                        order.document_id,
                        Severity.MEDIUM,
                        order.amount,
                        order.currency,
                        "Sales order has no billing document",
                        correlation_id,
                        {"sales_order_status": order.status},
                    )
                )

        for billing in billings:
            if not billing.accounting_document_id and not billing.cancelled:
                exceptions.append(
                    self._exception(
                        "SD002",
                        Module.CROSS,
                        "O2C",
                        billing.document_id,
                        self._severity(billing.amount, Severity.HIGH),
                        billing.amount,
                        billing.currency,
                        "Investigate the missing FI accounting document",
                        correlation_id,
                        {"sales_order_id": billing.sales_order_id, "accounting_document": None},
                        exception_type="BILLING_WITHOUT_FI",
                    )
                )
            order = orders.get(billing.sales_order_id or "")
            if not order and billing.sales_order_id:
                exceptions.append(
                    self._exception(
                        "CROSS004",
                        Module.CROSS,
                        "O2C",
                        billing.document_id,
                        Severity.HIGH,
                        billing.amount,
                        billing.currency,
                        "Repair or investigate the broken sales-order reference",
                        correlation_id,
                        {"missing_sales_order_id": billing.sales_order_id},
                    )
                )
            elif order:
                if order.currency != billing.currency:
                    exceptions.append(
                        self._exception(
                            "SD005",
                            Module.SD,
                            "O2C",
                            billing.document_id,
                            Severity.HIGH,
                            billing.amount,
                            billing.currency,
                            "Review currency mismatch",
                            correlation_id,
                            {
                                "order_currency": order.currency,
                                "billing_currency": billing.currency,
                            },
                        )
                    )
                if order.amount and billing.amount != order.amount:
                    exceptions.append(
                        self._exception(
                            "SD004",
                            Module.SD,
                            "O2C",
                            billing.document_id,
                            Severity.HIGH,
                            abs(billing.amount - order.amount),
                            billing.currency,
                            "Review billing value variance",
                            correlation_id,
                            {
                                "order_amount": str(order.amount),
                                "billing_amount": str(billing.amount),
                            },
                        )
                    )
        return exceptions

    def p2p(
        self,
        purchase_orders: list[PurchaseOrder],
        invoices: list[SupplierInvoice],
        correlation_id: UUID,
    ) -> list[ExceptionRecord]:
        exceptions: list[ExceptionRecord] = []
        orders = {po.document_id: po for po in purchase_orders}
        duplicate_keys = Counter(
            (invoice.supplier, invoice.amount, invoice.currency, invoice.document_date)
            for invoice in invoices
        )
        today = datetime.now(UTC).date()

        for invoice in invoices:
            po = orders.get(invoice.purchase_order_id or "")
            if not po:
                exceptions.append(
                    self._exception(
                        "MM003",
                        Module.MM,
                        "P2P",
                        invoice.document_id,
                        Severity.HIGH,
                        invoice.amount,
                        invoice.currency,
                        "Validate invoice without purchase order",
                        correlation_id,
                        {"purchase_order_id": invoice.purchase_order_id},
                    )
                )
                continue

            if (
                invoice.blocked
                and invoice.document_date
                and (today - invoice.document_date >= timedelta(days=self.blocked_invoice_sla_days))
            ):
                exceptions.append(
                    self._exception(
                        "MM004",
                        Module.MM,
                        "P2P",
                        invoice.document_id,
                        Severity.HIGH,
                        invoice.amount,
                        invoice.currency,
                        "Review blocked invoice before release",
                        correlation_id,
                        {"blocked_since": invoice.document_date.isoformat()},
                        True,
                    )
                )

            tolerance = po.amount * self.invoice_tolerance_percent / Decimal("100")
            variance = invoice.amount - po.amount
            if variance > tolerance:
                exceptions.append(
                    self._exception(
                        "MM005",
                        Module.MM,
                        "P2P",
                        invoice.document_id,
                        self._severity(variance, Severity.HIGH),
                        variance,
                        invoice.currency,
                        "Review price variance; do not release automatically",
                        correlation_id,
                        {
                            "po_amount": str(po.amount),
                            "invoice_amount": str(invoice.amount),
                            "tolerance_percent": str(self.invoice_tolerance_percent),
                        },
                        True,
                        exception_type="PO_INVOICE_PRICE_VARIANCE",
                    )
                )

            key = (invoice.supplier, invoice.amount, invoice.currency, invoice.document_date)
            if duplicate_keys[key] > 1:
                exceptions.append(
                    self._exception(
                        "MM007",
                        Module.MM,
                        "P2P",
                        invoice.document_id,
                        Severity.CRITICAL,
                        invoice.amount,
                        invoice.currency,
                        "Block payment and investigate duplicate",
                        correlation_id,
                        {"duplicate_signature_count": duplicate_keys[key]},
                        True,
                    )
                )
        return exceptions

    def fi(self, entries: list[JournalEntry], correlation_id: UUID) -> list[ExceptionRecord]:
        exceptions: list[ExceptionRecord] = []
        duplicate_keys = Counter(
            (entry.company_code, entry.reference_document, entry.amount, entry.posting_date)
            for entry in entries
        )
        for entry in entries:
            key = (entry.company_code, entry.reference_document, entry.amount, entry.posting_date)
            if duplicate_keys[key] > 1:
                exceptions.append(
                    self._exception(
                        "FI001",
                        Module.FI,
                        "R2R",
                        entry.document_id,
                        Severity.CRITICAL,
                        entry.amount,
                        entry.currency,
                        "Investigate possible duplicate journal entry",
                        correlation_id,
                        {"duplicate_signature_count": duplicate_keys[key]},
                        True,
                    )
                )
            if entry.amount >= self.critical_amount:
                exceptions.append(
                    self._exception(
                        "FI002",
                        Module.FI,
                        "R2R",
                        entry.document_id,
                        Severity.HIGH,
                        entry.amount,
                        entry.currency,
                        "Validate approval threshold and supporting evidence",
                        correlation_id,
                        {"approval_threshold": str(self.critical_amount)},
                        True,
                    )
                )
        return exceptions

    def _severity(self, amount: Decimal, minimum: Severity) -> Severity:
        return Severity.CRITICAL if amount >= self.critical_amount else minimum

    @staticmethod
    def _exception(
        rule_id: str,
        module: Module,
        process: str,
        document_id: str,
        severity: Severity,
        amount: Decimal,
        currency: str,
        action: str,
        correlation_id: UUID,
        evidence: dict,
        approval_required: bool = False,
        *,
        exception_type: str | None = None,
    ) -> ExceptionRecord:
        return ExceptionRecord(
            exception_type=exception_type or rule_id,
            module=module,
            process=process,
            source_document_id=document_id,
            severity=severity,
            amount_at_risk=amount,
            currency=currency,
            rule_id=rule_id,
            evidence=evidence,
            recommended_action=action,
            approval_required=approval_required,
            correlation_id=correlation_id,
        )
