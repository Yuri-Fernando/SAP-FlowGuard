from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from flowguard.domain.models import BillingDocument, PurchaseOrder, SalesOrder, SupplierInvoice
from flowguard.rules import RulesEngine


def test_billing_without_fi_triggers_cross_module_exception():
    order = SalesOrder(document_id="SO1", amount=Decimal("125000"), currency="BRL")
    billing = BillingDocument(
        document_id="B1",
        sales_order_id="SO1",
        accounting_document_id=None,
        amount=Decimal("125000"),
        currency="BRL",
    )

    exceptions = RulesEngine().o2c([order], [billing], uuid4())

    missing_fi = next(item for item in exceptions if item.rule_id == "SD002")
    assert missing_fi.exception_type == "BILLING_WITHOUT_FI"
    assert missing_fi.severity.value == "CRITICAL"


def test_price_variance_is_deterministic_and_requires_approval():
    po = PurchaseOrder(document_id="PO1", amount=Decimal("100000"), currency="BRL")
    invoice = SupplierInvoice(
        document_id="INV1",
        purchase_order_id="PO1",
        amount=Decimal("107500"),
        currency="BRL",
        blocked=True,
        document_date=date.today() - timedelta(days=7),
    )

    exceptions = RulesEngine().p2p([po], [invoice], uuid4())

    variance = next(item for item in exceptions if item.rule_id == "MM005")
    assert variance.amount_at_risk == Decimal("7500")
    assert variance.approval_required is True


def test_duplicate_invoice_signature_triggers_mm007():
    po = PurchaseOrder(document_id="PO1", amount=Decimal("100"), currency="BRL")
    common = {
        "purchase_order_id": "PO1",
        "supplier": "SUP1",
        "amount": Decimal("100"),
        "currency": "BRL",
        "document_date": date(2026, 9, 1),
    }
    invoices = [
        SupplierInvoice(document_id="INV1", **common),
        SupplierInvoice(document_id="INV2", **common),
    ]

    exceptions = RulesEngine().p2p([po], invoices, uuid4())

    assert len([item for item in exceptions if item.rule_id == "MM007"]) == 2
