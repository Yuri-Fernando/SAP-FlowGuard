import asyncio
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response

from mock_sap.data import SCENARIOS, load_scenario

app = FastAPI(
    title="SAP FlowGuard Mock S/4HANA",
    version="0.1.0",
    description="OData-like SAP simulator for safe, reproducible FI/SD/MM demonstrations.",
)
app.state.scenario = os.getenv("DEMO_SCENARIO", "billing_without_fi")
app.state.data = load_scenario(app.state.scenario)


@app.middleware("http")
async def inject_failures(request: Request, call_next):
    forced_error = request.headers.get("x-mock-error")
    if forced_error in {"401", "403", "404", "429", "500"}:
        return Response(status_code=int(forced_error), content=f"Injected HTTP {forced_error}")
    if app.state.scenario == "api_timeout" and request.url.path != "/mock/scenario":
        await asyncio.sleep(5)
    latency_ms = int(request.headers.get("x-mock-latency-ms", "0"))
    if latency_ms:
        await asyncio.sleep(min(latency_ms, 10000) / 1000)
    return await call_next(request)


def odata_v2(request: Request, rows: list[dict], top: int, skip: int) -> dict:
    page = rows[skip : skip + top]
    data: dict[str, Any] = {"results": page}
    if skip + top < len(rows):
        data["__next"] = str(request.url.include_query_params(**{"$skip": skip + top, "$top": top}))
    return {"d": data}


def odata_v4(request: Request, rows: list[dict], top: int, skip: int) -> dict:
    page = rows[skip : skip + top]
    data: dict[str, Any] = {"@odata.context": "$metadata#PurchaseOrder", "value": page}
    if skip + top < len(rows):
        data["@odata.nextLink"] = str(
            request.url.include_query_params(**{"$skip": skip + top, "$top": top})
        )
    return data


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "mock-sap", "scenario": app.state.scenario}


@app.get("/mock/scenarios")
async def scenarios():
    return {"available": sorted(SCENARIOS), "active": app.state.scenario}


@app.post("/mock/scenario/{name}")
async def activate_scenario(name: str):
    try:
        app.state.data = load_scenario(name)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    app.state.scenario = name
    return {"active": name, "records": {key: len(value) for key, value in app.state.data.items()}}


@app.get("/sap/opu/odata/sap/API_SALES_ORDER_SRV/$metadata")
async def sales_metadata():
    return Response(
        content='<?xml version="1.0"?><edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx"><edmx:DataServices m:DataServiceVersion="2.0" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata"/></edmx:Edmx>',
        media_type="application/xml",
    )


@app.get("/sap/opu/odata/sap/API_SALES_ORDER_SRV/A_SalesOrder")
async def sales_orders(
    request: Request,
    top: int = Query(20, alias="$top", ge=1, le=1000),
    skip: int = Query(0, alias="$skip", ge=0),
):
    return odata_v2(request, app.state.data["sales_orders"], top, skip)


@app.get("/sap/opu/odata/sap/API_BILLING_DOCUMENT_SRV/A_BillingDocument")
async def billing_documents(
    request: Request,
    top: int = Query(20, alias="$top", ge=1, le=1000),
    skip: int = Query(0, alias="$skip", ge=0),
):
    return odata_v2(request, app.state.data["billings"], top, skip)


@app.get("/sap/opu/odata4/sap/api_purchaseorder_2/srvd_a2x/sap/purchaseorder/0001/PurchaseOrder")
async def purchase_orders(
    request: Request,
    top: int = Query(20, alias="$top", ge=1, le=1000),
    skip: int = Query(0, alias="$skip", ge=0),
):
    return odata_v4(request, app.state.data["purchase_orders"], top, skip)


@app.get("/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV_0001/A_SupplierInvoice")
async def supplier_invoices(
    request: Request,
    top: int = Query(20, alias="$top", ge=1, le=1000),
    skip: int = Query(0, alias="$skip", ge=0),
):
    return odata_v2(request, app.state.data["supplier_invoices"], top, skip)


@app.get("/mock/fi/journal-entries")
async def journal_entries(
    request: Request,
    top: int = Query(20, alias="$top", ge=1, le=1000),
    skip: int = Query(0, alias="$skip", ge=0),
):
    return odata_v4(request, app.state.data["journal_entries"], top, skip)


@app.get("/mock/csrf")
async def csrf(response: Response, x_csrf_token: str | None = Header(None)):
    if x_csrf_token and x_csrf_token.lower() == "fetch":
        response.headers["x-csrf-token"] = "flowguard-mock-csrf-token"
    return {"csrf": "issued"}


@app.post("/mock/actions/{action}")
async def action(
    action: str,
    payload: dict,
    response: Response,
    x_csrf_token: str | None = Header(None),
    if_match: str | None = Header(None),
):
    if app.state.scenario == "csrf_failure" or x_csrf_token != "flowguard-mock-csrf-token":
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    if app.state.scenario == "etag_conflict" or if_match not in {"*", 'W/"1"'}:
        raise HTTPException(status_code=412, detail="ETag precondition failed")
    allowed = {"post_journal_entry", "cancel_billing_document", "release_supplier_invoice"}
    if action not in allowed:
        raise HTTPException(status_code=404, detail="Unknown mock action")
    response.headers["etag"] = 'W/"2"'
    return {
        "status": "SIMULATED",
        "action": action,
        "payload": payload,
        "scenario": app.state.scenario,
    }
