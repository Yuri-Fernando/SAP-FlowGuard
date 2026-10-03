import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from flowguard.domain.models import Approval, ApprovalState, ExceptionRecord

UTC = timezone.utc


class Base(DeclarativeBase):
    pass


class ExceptionRow(Base):
    __tablename__ = "flowguard_exceptions"

    exception_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rule_id: Mapped[str] = mapped_column(String(32), index=True)
    source_document_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApprovalRow(Base):
    __tablename__ = "flowguard_approvals"

    approval_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exception_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditRow(Base):
    __tablename__ = "flowguard_audit_events"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyRow(Base):
    __tablename__ = "flowguard_idempotency"

    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Repository:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _fingerprint(exception: ExceptionRecord) -> str:
        value = f"{exception.rule_id}|{exception.source_document_id}|{exception.status}"
        return hashlib.sha256(value.encode()).hexdigest()

    def save_exceptions(self, exceptions: list[ExceptionRecord]) -> int:
        inserted = 0
        now = datetime.now(UTC)
        with Session(self.engine) as session:
            for exception in exceptions:
                fingerprint = self._fingerprint(exception)
                existing = session.scalar(
                    select(ExceptionRow).where(ExceptionRow.fingerprint == fingerprint)
                )
                payload = exception.model_dump(mode="json")
                if existing:
                    existing.payload = payload
                    existing.updated_at = now
                    continue
                session.add(
                    ExceptionRow(
                        exception_id=str(exception.exception_id),
                        fingerprint=fingerprint,
                        rule_id=exception.rule_id,
                        source_document_id=exception.source_document_id,
                        status=exception.status.value,
                        payload=payload,
                        created_at=now,
                        updated_at=now,
                    )
                )
                inserted += 1
            session.commit()
        return inserted

    def list_exceptions(self) -> list[ExceptionRecord]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ExceptionRow).order_by(ExceptionRow.created_at.desc())
            ).all()
            return [ExceptionRecord.model_validate(row.payload) for row in rows]

    def get_exception(self, exception_id: UUID) -> ExceptionRecord | None:
        with Session(self.engine) as session:
            row = session.get(ExceptionRow, str(exception_id))
            return ExceptionRecord.model_validate(row.payload) if row else None

    def save_approval(self, approval: Approval) -> None:
        now = datetime.now(UTC)
        with Session(self.engine) as session:
            row = session.get(ApprovalRow, str(approval.approval_id))
            if row:
                row.state = approval.state.value
                row.payload = approval.model_dump(mode="json")
                row.updated_at = now
            else:
                session.add(
                    ApprovalRow(
                        approval_id=str(approval.approval_id),
                        exception_id=str(approval.exception_id),
                        state=approval.state.value,
                        payload=approval.model_dump(mode="json"),
                        updated_at=now,
                    )
                )
            session.commit()

    def get_approval(self, approval_id: UUID) -> Approval | None:
        with Session(self.engine) as session:
            row = session.get(ApprovalRow, str(approval_id))
            return Approval.model_validate(row.payload) if row else None

    def list_approvals(self, state: ApprovalState | None = None) -> list[Approval]:
        with Session(self.engine) as session:
            statement = select(ApprovalRow).order_by(ApprovalRow.updated_at.desc())
            if state:
                statement = statement.where(ApprovalRow.state == state.value)
            rows = session.scalars(statement).all()
            return [Approval.model_validate(row.payload) for row in rows]

    def audit(self, correlation_id: UUID, event_type: str, actor: str, payload: dict) -> None:
        with Session(self.engine) as session:
            session.add(
                AuditRow(
                    correlation_id=str(correlation_id),
                    event_type=event_type,
                    actor=actor,
                    payload=json.loads(json.dumps(payload, default=str)),
                    occurred_at=datetime.now(UTC),
                )
            )
            session.commit()

    def idempotent_result(self, key: str) -> dict | None:
        with Session(self.engine) as session:
            row = session.get(IdempotencyRow, key)
            return json.loads(row.result_json) if row and row.result_json else None

    def save_idempotent_result(self, key: str, action: str, result: dict) -> None:
        with Session(self.engine) as session:
            session.add(
                IdempotencyRow(
                    idempotency_key=key,
                    action=action,
                    result_json=json.dumps(result, default=str),
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
