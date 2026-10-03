import os
from decimal import Decimal

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="SAP FlowGuard Dashboard")
API_URL = os.getenv("FLOWGUARD_API_URL", "http://localhost:8000").rstrip("/")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/summary")
async def summary():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{API_URL}/exceptions")
        response.raise_for_status()
        exceptions = response.json()
    open_items = [item for item in exceptions if item["status"] == "OPEN"]
    risk = sum(Decimal(str(item["amount_at_risk"])) for item in open_items)
    return {
        "open": len(open_items),
        "critical": sum(item["severity"] == "CRITICAL" for item in open_items),
        "amount_at_risk": str(risk),
        "exceptions": open_items[:20],
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>SAP FlowGuard</title><style>
:root{font-family:Inter,Segoe UI,sans-serif;color:#e8edf5;background:#08111f}body{max-width:1180px;margin:0 auto;padding:32px}
h1{margin-bottom:4px}.sub{color:#91a4be}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}
.card,table{background:#101d30;border:1px solid #243650;border-radius:12px}.card{padding:22px}.value{font-size:32px;font-weight:700;color:#57d6a2}
table{width:100%;border-collapse:collapse;overflow:hidden}th,td{text-align:left;padding:12px;border-bottom:1px solid #243650}th{color:#91a4be}
.CRITICAL{color:#ff6b7a}.HIGH{color:#ffb454}@media(max-width:700px){.cards{grid-template-columns:1fr}body{padding:18px}}
</style></head><body><h1>SAP FlowGuard</h1><div class="sub">FI / SD / MM Exception Control Tower · mock/sandbox/hybrid/live</div>
<div class="cards"><div class="card">Exceções abertas<div id="open" class="value">–</div></div><div class="card">Críticas<div id="critical" class="value">–</div></div><div class="card">Valor em risco<div id="risk" class="value">–</div></div></div>
<table><thead><tr><th>Regra</th><th>Documento</th><th>Processo</th><th>Severidade</th><th>Risco</th></tr></thead><tbody id="rows"></tbody></table>
<script>async function load(){const r=await fetch('/api/summary');const d=await r.json();open.textContent=d.open;critical.textContent=d.critical;risk.textContent=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(d.amount_at_risk);rows.innerHTML=d.exceptions.map(x=>`<tr><td>${x.rule_id}</td><td>${x.source_document_id}</td><td>${x.process}</td><td class="${x.severity}">${x.severity}</td><td>${x.currency} ${x.amount_at_risk}</td></tr>`).join('')}load();setInterval(load,15000)</script>
</body></html>"""
