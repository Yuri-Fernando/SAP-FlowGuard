import asyncio

import httpx

from apps.dashboard import monitor


def test_n8n_monitor_degrades_without_api_key(monkeypatch):
    monkeypatch.setattr(monitor, "N8N_API_KEY", "")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/healthz"
        return httpx.Response(200, json={"status": "ok"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await monitor._n8n_status(client)

    result = asyncio.run(run())
    assert result["online"] is True
    assert result["api_configured"] is False
    assert result["workflows"] == []


def test_n8n_monitor_reads_public_api(monkeypatch):
    monkeypatch.setattr(monitor, "N8N_API_KEY", "local-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        assert request.headers["X-N8N-API-KEY"] == "local-test-key"
        if request.url.path == "/api/v1/workflows":
            return httpx.Response(
                200, json={"data": [{"id": "1", "name": "WF-01", "active": True}]}
            )
        if request.url.path == "/api/v1/executions":
            return httpx.Response(200, json={"data": [{"id": "10", "status": "success"}]})
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await monitor._n8n_status(client)

    result = asyncio.run(run())
    assert result["online"] is True
    assert result["api_configured"] is True
    assert result["workflows"][0]["active"] is True
    assert result["executions"][0]["status"] == "success"
