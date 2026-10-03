from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


class Module(str, Enum):
    SD = "SD"
    MM = "MM"
    FI = "FI"
    CROSS = "CROSS"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ApprovalState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class MoneyDocument(BaseModel):
    document_id: str
    company_code: str = "1000"
    amount: Decimal = Decimal("0")
    currency: str = "BRL"
    document_date: date | None = None
    status: str = "OPEN"
    source_system: str = "SAP"
    raw_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)


class SalesOrder(MoneyDocument):
    sales_organization: str | None = None
    sold_to_party: str | None = None
    billing_document_ids: list[str] = Field(default_factory=list)


class BillingDocument(MoneyDocument):
    sales_order_id: str | None = None
    accounting_document_id: str | None = None
    cancelled: bool = False


class PurchaseOrder(MoneyDocument):
    supplier: str | None = None
    goods_receipt_amount: Decimal = Decimal("0")


class SupplierInvoice(MoneyDocument):
    purchase_order_id: str | None = None
    supplier: str | None = None
    blocked: bool = False
    quantity: Decimal | None = None


class JournalEntry(MoneyDocument):
    reference_document: str | None = None
    posting_date: date | None = None


class ExceptionRecord(BaseModel):
    exception_id: UUID = Field(default_factory=uuid4)
    exception_type: str
    module: Module
    process: str
    source_document_id: str
    related_document_ids: list[str] = Field(default_factory=list)
    severity: Severity
    amount_at_risk: Decimal = Decimal("0")
    currency: str = "BRL"
    rule_id: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=utc_now)
    status: ExceptionStatus = ExceptionStatus.OPEN
    assigned_to: str | None = None
    recommended_action: str | None = None
    ai_summary: str | None = None
    approval_required: bool = False
    correlation_id: UUID


class Approval(BaseModel):
    approval_id: UUID = Field(default_factory=uuid4)
    exception_id: UUID
    action: str
    requested_by: str
    requested_at: datetime = Field(default_factory=utc_now)
    state: ApprovalState = ApprovalState.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str | None = None


class CapabilityReport(BaseModel):
    provider: str
    healthy: bool
    odata_v2: bool = False
    odata_v4: bool = False
    sales_order_read: bool = False
    sales_order_write: bool = False
    purchase_order_read: bool = False
    supplier_invoice_read: bool = False
    supplier_invoice_release: bool = False
    journal_entry_read: bool = False
    journal_entry_post: bool = False
    csrf: bool = False
    etag: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class MonitorResult(BaseModel):
    workflow: str
    correlation_id: UUID
    documents_processed: int
    exceptions: list[ExceptionRecord]
    started_at: datetime
    finished_at: datetime
