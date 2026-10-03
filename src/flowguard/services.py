from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from flowguard.config import Settings
from flowguard.domain.models import (
    Approval,
    ApprovalDecision,
    ApprovalState,
    MonitorResult,
)
from flowguard.persistence import Repository
from flowguard.providers.base import SapProvider, SapWriteError
from flowguard.rules import RulesEngine

UTC = timezone.utc


class MonitorService:
    def __init__(self, provider: SapProvider, rules: RulesEngine, repository: Repository) -> None:
        self.provider = provider
        self.rules = rules
        self.repository = repository

    async def run(self, workflow: str, correlation_id: UUID | None = None) -> MonitorResult:
        correlation_id = correlation_id or uuid4()
        started = datetime.now(UTC)
        workflow = workflow.lower()
        if workflow == "o2c":
            orders = await self.provider.list_sales_orders()
            billings = await self.provider.list_billing_documents()
            exceptions = self.rules.o2c(orders, billings, correlation_id)
            count = len(orders) + len(billings)
        elif workflow == "p2p":
            orders = await self.provider.list_purchase_orders()
            invoices = await self.provider.list_supplier_invoices()
            exceptions = self.rules.p2p(orders, invoices, correlation_id)
            count = len(orders) + len(invoices)
        elif workflow == "fi":
            entries = await self.provider.list_journal_entries()
            exceptions = self.rules.fi(entries, correlation_id)
            count = len(entries)
        else:
            raise ValueError(f"Unknown workflow: {workflow}")

        self.repository.save_exceptions(exceptions)
        self.repository.audit(
            correlation_id,
            "MONITOR_COMPLETED",
            "system",
            {"workflow": workflow, "documents_processed": count, "exceptions": len(exceptions)},
        )
        return MonitorResult(
            workflow=workflow,
            correlation_id=correlation_id,
            documents_processed=count,
            exceptions=exceptions,
            started_at=started,
            finished_at=datetime.now(UTC),
        )


class ApprovalService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def request(self, exception_id: UUID, action: str, requested_by: str) -> Approval:
        if not self.repository.get_exception(exception_id):
            raise LookupError("Exception not found")
        approval = Approval(exception_id=exception_id, action=action, requested_by=requested_by)
        self.repository.save_approval(approval)
        self.repository.audit(
            exception_id, "APPROVAL_REQUESTED", requested_by, approval.model_dump(mode="json")
        )
        return approval

    def decide(
        self, approval_id: UUID, decision: ApprovalDecision, decided_by: str, reason: str | None
    ) -> Approval:
        approval = self.repository.get_approval(approval_id)
        if not approval:
            raise LookupError("Approval not found")
        if approval.state != ApprovalState.PENDING:
            raise ValueError(f"Approval is already {approval.state}")
        approval.state = (
            ApprovalState.APPROVED
            if decision == ApprovalDecision.APPROVE
            else ApprovalState.REJECTED
        )
        approval.decided_by = decided_by
        approval.decided_at = datetime.now(UTC)
        approval.reason = reason
        self.repository.save_approval(approval)
        self.repository.audit(
            approval.exception_id,
            "APPROVAL_DECIDED",
            decided_by,
            {"approval_id": str(approval_id), "decision": decision.value, "reason": reason},
        )
        return approval


class WritebackService:
    ACTION_FLAGS = {
        "post_journal_entry": "allow_fi_posting",
        "cancel_billing_document": "allow_billing_cancel",
        "release_supplier_invoice": "allow_invoice_release",
    }

    def __init__(self, provider: SapProvider, repository: Repository, settings: Settings) -> None:
        self.provider = provider
        self.repository = repository
        self.settings = settings

    async def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        idempotency_key: str,
        actor: str,
        correlation_id: UUID,
        approval_id: UUID | None,
        etag: str | None,
    ) -> dict:
        previous = self.repository.idempotent_result(idempotency_key)
        if previous:
            return {**previous, "idempotent_replay": True}
        if not self.settings.enable_sap_write:
            raise SapWriteError("SAP writes are disabled: ENABLE_SAP_WRITE=false")
        flag = self.ACTION_FLAGS.get(action)
        if flag and not getattr(self.settings, flag):
            raise SapWriteError(f"Action {action} is disabled by {flag.upper()}=false")
        if self.settings.require_human_approval:
            if not approval_id:
                raise SapWriteError("An approval_id is required")
            approval = self.repository.get_approval(approval_id)
            if not approval or approval.state != ApprovalState.APPROVED:
                raise SapWriteError("Approval is missing or not APPROVED")
            if approval.action != action:
                raise SapWriteError("Approved action does not match requested writeback")

        result = await self.provider.write(action, payload, etag)
        self.repository.save_idempotent_result(idempotency_key, action, result)
        self.repository.audit(
            correlation_id, "SAP_WRITEBACK", actor, {"action": action, "result": result}
        )
        return result
