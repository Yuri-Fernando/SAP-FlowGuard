from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from flowguard.config import get_settings
from flowguard.domain.models import ApprovalDecision, ApprovalState
from flowguard.persistence import Repository
from flowguard.providers import SapWriteError, create_provider
from flowguard.rules import RulesEngine
from flowguard.services import ApprovalService, MonitorService, WritebackService


class ApprovalRequest(BaseModel):
    exception_id: UUID
    action: str
    requested_by: str = "flowguard-operator"


class DecisionRequest(BaseModel):
    decision: ApprovalDecision
    decided_by: str
    reason: str | None = None


class WritebackRequest(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=160)
    actor: str
    correlation_id: UUID = Field(default_factory=uuid4)
    approval_id: UUID | None = None
    etag: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repository = Repository(settings.database_url)
    repository.create_schema()
    provider = create_provider(settings)
    app.state.settings = settings
    app.state.repository = repository
    app.state.provider = provider
    app.state.monitor = MonitorService(provider, RulesEngine(), repository)
    app.state.approvals = ApprovalService(repository)
    app.state.writeback = WritebackService(provider, repository, settings)
    yield
    await provider.close()


app = FastAPI(
    title="SAP FlowGuard API",
    version="0.1.0",
    description="FI/SD/MM exception control tower with safe SAP adapters.",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "name": "SAP FlowGuard",
        "docs": "/docs",
        "safety": "SAP writes are disabled by default",
    }


@app.get("/health")
async def health():
    provider_ok = await app.state.provider.health_check()
    return {
        "status": "ok" if provider_ok else "degraded",
        "sap_mode": app.state.settings.sap_mode,
        "provider_healthy": provider_ok,
        "sap_write_enabled": app.state.settings.enable_sap_write,
    }


@app.get("/capabilities")
async def capabilities():
    return await app.state.provider.discover_capabilities()


@app.post("/runs/{workflow}")
async def run_monitor(workflow: str, x_correlation_id: str | None = Header(None)):
    if workflow.lower() not in {"o2c", "p2p", "fi"}:
        raise HTTPException(status_code=404, detail="Workflow must be o2c, p2p or fi")
    try:
        try:
            correlation_id = UUID(x_correlation_id) if x_correlation_id else None
        except ValueError:
            correlation_id = uuid4()
        return await app.state.monitor.run(workflow, correlation_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/exceptions")
async def exceptions():
    return app.state.repository.list_exceptions()


@app.post("/approvals", status_code=201)
async def request_approval(request: ApprovalRequest):
    try:
        return app.state.approvals.request(
            request.exception_id, request.action, request.requested_by
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/approvals")
async def approvals(state: ApprovalState | None = Query(None)):
    return app.state.repository.list_approvals(state)


@app.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: UUID, request: DecisionRequest):
    try:
        return app.state.approvals.decide(
            approval_id, request.decision, request.decided_by, request.reason
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/writebacks")
async def writeback(request: WritebackRequest):
    try:
        return await app.state.writeback.execute(**request.model_dump())
    except SapWriteError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
