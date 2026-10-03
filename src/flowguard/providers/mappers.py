from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flowguard.domain.models import (
    BillingDocument,
    JournalEntry,
    PurchaseOrder,
    SalesOrder,
    SupplierInvoice,
)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    if text.startswith("/Date("):
        milliseconds = int(text.removeprefix("/Date(").split(")", 1)[0])
        return datetime.fromtimestamp(milliseconds / 1000).date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def sales_order(raw: dict[str, Any]) -> SalesOrder:
    return SalesOrder(
        document_id=str(raw.get("SalesOrder") or raw.get("document_id")),
        company_code=str(raw.get("CompanyCode") or raw.get("company_code") or "1000"),
        sales_organization=raw.get("SalesOrganization"),
        sold_to_party=raw.get("SoldToParty"),
        amount=_decimal(raw.get("TotalNetAmount") or raw.get("amount")),
        currency=str(raw.get("TransactionCurrency") or raw.get("currency") or "BRL"),
        document_date=_date(raw.get("SalesOrderDate") or raw.get("document_date")),
        status=str(raw.get("OverallSDProcessStatus") or raw.get("status") or "OPEN"),
        raw_payload=raw,
    )


def billing_document(raw: dict[str, Any]) -> BillingDocument:
    return BillingDocument(
        document_id=str(raw.get("BillingDocument") or raw.get("document_id")),
        company_code=str(raw.get("CompanyCode") or raw.get("company_code") or "1000"),
        sales_order_id=raw.get("SalesDocument") or raw.get("sales_order_id"),
        accounting_document_id=raw.get("AccountingDocument") or raw.get("accounting_document_id"),
        amount=_decimal(raw.get("TotalNetAmount") or raw.get("amount")),
        currency=str(raw.get("TransactionCurrency") or raw.get("currency") or "BRL"),
        document_date=_date(raw.get("BillingDocumentDate") or raw.get("document_date")),
        cancelled=bool(raw.get("CancelledBillingDocument") or raw.get("cancelled", False)),
        status=str(raw.get("BillingDocumentIsCancelled") or raw.get("status") or "OPEN"),
        raw_payload=raw,
    )


def purchase_order(raw: dict[str, Any]) -> PurchaseOrder:
    return PurchaseOrder(
        document_id=str(raw.get("PurchaseOrder") or raw.get("document_id")),
        company_code=str(raw.get("CompanyCode") or raw.get("company_code") or "1000"),
        supplier=raw.get("Supplier") or raw.get("supplier"),
        amount=_decimal(raw.get("PurchaseOrderNetAmount") or raw.get("amount")),
        goods_receipt_amount=_decimal(
            raw.get("GoodsReceiptAmount") or raw.get("goods_receipt_amount")
        ),
        currency=str(raw.get("DocumentCurrency") or raw.get("currency") or "BRL"),
        document_date=_date(raw.get("PurchaseOrderDate") or raw.get("document_date")),
        status=str(raw.get("PurchasingProcessingStatus") or raw.get("status") or "OPEN"),
        raw_payload=raw,
    )


def supplier_invoice(raw: dict[str, Any]) -> SupplierInvoice:
    return SupplierInvoice(
        document_id=str(raw.get("SupplierInvoice") or raw.get("document_id")),
        company_code=str(raw.get("CompanyCode") or raw.get("company_code") or "1000"),
        purchase_order_id=raw.get("PurchaseOrder") or raw.get("purchase_order_id"),
        supplier=raw.get("InvoicingParty") or raw.get("supplier"),
        amount=_decimal(raw.get("InvoiceGrossAmount") or raw.get("amount")),
        currency=str(raw.get("DocumentCurrency") or raw.get("currency") or "BRL"),
        document_date=_date(raw.get("DocumentDate") or raw.get("document_date")),
        blocked=bool(raw.get("PaymentBlockingReason") or raw.get("blocked", False)),
        quantity=_decimal(raw.get("InvoicedQuantity")) if raw.get("InvoicedQuantity") else None,
        status=str(raw.get("SupplierInvoiceStatus") or raw.get("status") or "OPEN"),
        raw_payload=raw,
    )


def journal_entry(raw: dict[str, Any]) -> JournalEntry:
    return JournalEntry(
        document_id=str(raw.get("AccountingDocument") or raw.get("document_id")),
        company_code=str(raw.get("CompanyCode") or raw.get("company_code") or "1000"),
        reference_document=raw.get("ReferenceDocument") or raw.get("reference_document"),
        amount=_decimal(raw.get("AmountInCompanyCodeCurrency") or raw.get("amount")),
        currency=str(raw.get("CompanyCodeCurrency") or raw.get("currency") or "BRL"),
        document_date=_date(raw.get("DocumentDate") or raw.get("document_date")),
        posting_date=_date(raw.get("PostingDate") or raw.get("posting_date")),
        status=str(raw.get("status") or "POSTED"),
        raw_payload=raw,
    )
