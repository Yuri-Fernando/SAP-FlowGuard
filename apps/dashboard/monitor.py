import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="SAP FlowGuard n8n Monitor")
API_URL = os.getenv("FLOWGUARD_API_URL", "http://localhost:8000").rstrip("/")
N8N_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678").rstrip("/")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
INDEX_HTML = Path(__file__).with_name("index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _flowguard_get(client: httpx.AsyncClient, path: str, fallback: Any) -> Any:
    try:
        response = await client.get(f"{API_URL}{path}")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return fallback


async def _n8n_status(client: httpx.AsyncClient) -> dict[str, Any]:
    result: dict[str, Any] = {
        "online": False,
        "api_configured": bool(N8N_API_KEY),
        "workflows": [],
        "executions": [],
        "message": "n8n está offline.",
    }
    try:
        health_response = await client.get(f"{N8N_URL}/healthz")
        result["online"] = health_response.is_success
    except httpx.HTTPError:
        return result

    if not N8N_API_KEY:
        result["message"] = "Configure N8N_API_KEY para listar workflows e execuções."
        return result

    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    try:
        workflows_response, executions_response = await asyncio.gather(
            client.get(f"{N8N_URL}/api/v1/workflows", params={"limit": 100}, headers=headers),
            client.get(
                f"{N8N_URL}/api/v1/executions",
                params={"limit": 30, "includeData": "false"},
                headers=headers,
            ),
        )
        workflows_response.raise_for_status()
        executions_response.raise_for_status()
        result["workflows"] = workflows_response.json().get("data", [])
        result["executions"] = executions_response.json().get("data", [])
        result["message"] = "Nenhum registro retornado pelo n8n."
    except (httpx.HTTPError, ValueError) as error:
        result["message"] = f"n8n API indisponível: {type(error).__name__}"
    return result


@app.get("/api/summary")
async def summary():
    async with httpx.AsyncClient(timeout=8) as client:
        api_health, exceptions, approvals, n8n = await asyncio.gather(
            _flowguard_get(client, "/health", {}),
            _flowguard_get(client, "/exceptions", []),
            _flowguard_get(client, "/approvals", []),
            _n8n_status(client),
        )

    open_items = [item for item in exceptions if item["status"] == "OPEN"]
    risk = sum(Decimal(str(item["amount_at_risk"])) for item in open_items)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "api": {
            "online": bool(api_health),
            "sap_mode": api_health.get("sap_mode"),
            "provider_healthy": api_health.get("provider_healthy", False),
        },
        "n8n": n8n,
        "metrics": {
            "open": len(open_items),
            "critical": sum(item["severity"] == "CRITICAL" for item in open_items),
            "amount_at_risk": str(risk),
            "pending_approvals": sum(item["state"] == "PENDING" for item in approvals),
            "active_workflows": sum(item.get("active", False) for item in n8n["workflows"]),
        },
        "exceptions": open_items[:20],
        "approvals": approvals[:20],
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML.read_text(encoding="utf-8")
