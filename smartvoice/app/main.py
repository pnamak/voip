from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .ocs import MagnusBillingOcs, MockOcs, OcsError, get_ocs
from .reports import REPORTS, bound_dates, csv_text, in_date_range, matches_query, menu_items, normalize_row, summarize
from .sip_status import collect_sip_monitor
from .store import BssStore

APP_DIR = config.APP_DIR
_store: BssStore | None = None
_ocs: MagnusBillingOcs | MockOcs | None = None


def store() -> BssStore:
    global _store
    if _store is None:
        _store = BssStore()
    return _store


def ocs() -> MagnusBillingOcs | MockOcs:
    global _ocs
    if _ocs is None:
        _ocs = get_ocs()
    return _ocs


def reset_runtime() -> None:
    global _store, _ocs
    if _ocs is not None:
        _ocs.close()
    _store = None
    _ocs = None

app = FastAPI(
    title="SmartVoice BSS",
    description="Business Support System for VoIP operators. MagnusBilling is the OCS engine.",
    version="1.0.0",
)


class LoginIn(BaseModel):
    username: str
    password: str


class CustomerIn(BaseModel):
    username: str | None = None
    password: str | None = None
    firstname: str = ""
    lastname: str = ""
    email: str = ""
    company_name: str = ""
    credit: float = 0
    creditlimit: float = 0
    typepaid: int = 0
    id_plan: int | None = None
    id_user: int = 1
    note: str = ""
    active: int = 1


class ProductIn(BaseModel):
    name: str
    description: str = ""
    monthly_fee: float = 0
    included_minutes: int = 0
    kind: str = "prepaid"
    create_ocs_plan: bool = True
    ini_credit: float = 0


class PaymentIn(BaseModel):
    ocs_user_id: int
    amount: float
    method: str = "cash"
    reference: str = ""
    description: str = "SmartVoice BSS payment"


class NoteIn(BaseModel):
    note: str = ""


class InvoiceIn(BaseModel):
    ocs_user_id: int
    period: str = Field(description="Billing period such as 2026-08")


def _cookie_name() -> str:
    return "smartvoice_session"


def current_user(request: Request) -> str:
    user = store().session_user(request.cookies.get(_cookie_name()))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if rows is False or rows is None:
            return []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _user_kind(row: dict[str, Any]) -> str:
    group_id = int(row.get("id_group") or 0)
    group_name = str(row.get("idGroupname") or "")
    if group_id == 1 or group_name.lower().startswith("admin"):
        return "admin"
    if group_id == config.RESELLER_GROUP_ID or group_name.lower() in {"agent", "reseller"}:
        return "reseller"
    return "customer"


def _paid_kind(row: dict[str, Any]) -> str:
    return "postpaid" if int(row.get("typepaid") or 0) == 1 else "prepaid"


@app.get("/api/health")
def health() -> dict[str, Any]:
    ocs_health = ocs().health()
    return {
        "app": config.BRAND_NAME,
        "role": "bss",
        "ocs": ocs_health,
    }


@app.post("/api/login")
def login(payload: LoginIn, response: Response) -> dict[str, Any]:
    if not store().authenticate(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = store().create_session(payload.username)
    response.set_cookie(
        _cookie_name(),
        token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
        path="/",
    )
    return {"ok": True, "username": payload.username}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    store().drop_session(request.cookies.get(_cookie_name()))
    response.delete_cookie(_cookie_name())
    return {"ok": "signed out"}


@app.get("/api/session")
def session(user: str = Depends(current_user)) -> dict[str, Any]:
    return {
        "username": user,
        "brand": config.BRAND_NAME,
        "product": config.BRAND_PRODUCT,
        "ocs": ocs().health(),
    }


@app.get("/api/dashboard")
def dashboard(user: str = Depends(current_user)) -> dict[str, Any]:
    users = _rows(ocs().read("user", page=1, limit=500))
    customers = [row for row in users if _user_kind(row) == "customer"]
    resellers = [row for row in users if _user_kind(row) == "reseller"]
    prepaid = [row for row in customers if _paid_kind(row) == "prepaid"]
    postpaid = [row for row in customers if _paid_kind(row) == "postpaid"]
    wallet = sum(float(row.get("credit") or 0) for row in customers)
    refills = _rows(ocs().read("refill", page=1, limit=50))
    calls = _rows(ocs().read("call", page=1, limit=50))
    billed = sum(float(row.get("sessionbill") or 0) for row in calls)
    online = _rows(ocs().read("callOnLine", page=1, limit=50))
    sip = collect_sip_monitor(ocs())
    return {
        "customers": len(customers),
        "resellers": len(resellers),
        "prepaid": len(prepaid),
        "postpaid": len(postpaid),
        "ocs_wallet": round(wallet, 4),
        "usage_billed": round(billed, 4),
        "live_calls": len(online),
        "sip_devices": sip["counts"]["total"],
        "sip_registered": sip["counts"]["registered"],
        "sip_offline": sip["counts"]["offline"],
        "sip_in_call": sip["counts"]["in_call"],
        "recent_payments": refills[:8],
        "recent_calls": calls[:8],
        "sip": sip["rows"][:8],
        "ocs": ocs().health(),
    }


@app.get("/api/customers")
def customers(user: str = Depends(current_user)) -> dict[str, Any]:
    rows = [row for row in _rows(ocs().read("user", page=1, limit=500)) if _user_kind(row) == "customer"]
    for row in rows:
        row["bss_note"] = store().get_note(int(row["id"]))
        row["paid_kind"] = _paid_kind(row)
    return {"rows": rows, "count": len(rows)}


@app.post("/api/customers")
def create_customer(payload: CustomerIn, user: str = Depends(current_user)) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    note = data.pop("note", "")
    data["id_group"] = config.CLIENT_GROUP_ID
    data["active"] = payload.active
    result = ocs().create_user(data)
    created = result.get("data") if isinstance(result, dict) else None
    if created and note:
        store().set_note(int(created["id"]), note)
    if isinstance(result, dict) and result.get("success") is False:
        raise HTTPException(status_code=400, detail=result.get("errors") or "OCS rejected the customer")
    return result if isinstance(result, dict) else {"result": result}


@app.post("/api/customers/{ocs_user_id}/note")
def save_note(ocs_user_id: int, payload: NoteIn, user: str = Depends(current_user)) -> dict[str, str]:
    store().set_note(ocs_user_id, payload.note)
    return {"ok": "saved"}


@app.get("/api/resellers")
def resellers(user: str = Depends(current_user)) -> dict[str, Any]:
    users = _rows(ocs().read("user", page=1, limit=500))
    agents = [row for row in users if _user_kind(row) == "reseller"]
    for agent in agents:
        children = [row for row in users if str(row.get("id_user")) == str(agent["id"])]
        agent["customers"] = len(children)
        agent["customer_wallet"] = round(sum(float(row.get("credit") or 0) for row in children), 4)
        agent["bss_note"] = store().get_note(int(agent["id"]))
    return {"rows": agents, "count": len(agents)}


@app.post("/api/resellers")
def create_reseller(payload: CustomerIn, user: str = Depends(current_user)) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    note = data.pop("note", "")
    data["id_group"] = config.RESELLER_GROUP_ID
    data["typepaid"] = 1
    result = ocs().create_user(data)
    created = result.get("data") if isinstance(result, dict) else None
    if created and note:
        store().set_note(int(created["id"]), note)
    if isinstance(result, dict) and result.get("success") is False:
        raise HTTPException(status_code=400, detail=result.get("errors") or "OCS rejected the reseller")
    return result if isinstance(result, dict) else {"result": result}


@app.get("/api/products")
def products(user: str = Depends(current_user)) -> dict[str, Any]:
    plans = _rows(ocs().read("plan", page=1, limit=200))
    catalog = store().list_products()
    by_id = {int(row["id"]): row for row in plans if row.get("id") is not None}
    for item in catalog:
        plan_id = item.get("ocs_plan_id")
        item["ocs_plan"] = by_id.get(int(plan_id)) if plan_id else None
    return {"catalog": catalog, "ocs_plans": plans}


@app.post("/api/products")
def create_product(payload: ProductIn, user: str = Depends(current_user)) -> dict[str, Any]:
    plan_id = None
    if payload.create_ocs_plan:
        created = ocs().create(
            "plan",
            {"name": payload.name, "ini_credit": payload.ini_credit, "signup": 1 if payload.kind == "prepaid" else 0},
        )
        rows = _rows(created) if isinstance(created, dict) else []
        if rows:
            plan_id = rows[0].get("id")
        elif isinstance(created, dict) and created.get("success") is False:
            raise HTTPException(status_code=400, detail=created.get("errors") or "OCS plan create failed")
    item = store().add_product(
        {
            "name": payload.name,
            "description": payload.description,
            "ocs_plan_id": plan_id,
            "monthly_fee": payload.monthly_fee,
            "included_minutes": payload.included_minutes,
            "kind": payload.kind,
        }
    )
    return item


@app.get("/api/payments")
def payments(user: str = Depends(current_user)) -> dict[str, Any]:
    ocs_rows = _rows(ocs().read("refill", page=1, limit=200))
    return {"bss": store().list_payments(), "ocs": ocs_rows}


@app.post("/api/payments")
def create_payment(payload: PaymentIn, user: str = Depends(current_user)) -> dict[str, Any]:
    users = _rows(ocs().read("user", page=1, limit=500))
    target = next((row for row in users if int(row["id"]) == payload.ocs_user_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found in OCS")
    refill = ocs().create(
        "refill",
        {
            "id_user": payload.ocs_user_id,
            "credit": payload.amount,
            "payment": 1,
            "description": payload.description or f"{payload.method} {payload.reference}".strip(),
        },
    )
    refill_id = None
    rows = _rows(refill) if isinstance(refill, dict) else []
    if rows:
        refill_id = rows[0].get("id")
    if isinstance(refill, dict) and refill.get("success") is False:
        raise HTTPException(status_code=400, detail=refill.get("errors") or "OCS refill failed")
    recorded = store().add_payment(
        {
            "ocs_user_id": payload.ocs_user_id,
            "username": target.get("username"),
            "amount": payload.amount,
            "method": payload.method,
            "reference": payload.reference,
            "ocs_refill_id": refill_id,
        }
    )
    return {"bss": recorded, "ocs": refill}


@app.get("/api/usage")
def usage(user: str = Depends(current_user)) -> dict[str, Any]:
    return {
        "cdrs": _rows(ocs().read("call", page=1, limit=200)),
        "live": _rows(ocs().read("callOnLine", page=1, limit=100)),
        "ocs": ocs().health(),
    }


def _build_report(
    slug: str,
    q: str,
    date_from: str,
    date_to: str,
    page: int,
    limit: int,
) -> dict[str, Any]:
    spec = REPORTS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    client = ocs()
    client.clear_filter()
    try:
        if spec.date_field == "starttime":
            start, end = bound_dates(date_from, date_to)
            if start:
                client.set_filter("starttime", start, "gt", "date")
            if end:
                client.set_filter("starttime", end, "lt", "date")
        payload = client.read(spec.module, page=max(page, 1), limit=min(max(limit, 1), 1000))
    finally:
        client.clear_filter()
    raw = _rows(payload)
    total = payload.get("count", len(raw)) if isinstance(payload, dict) else len(raw)
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        total = len(raw)
    rows = [
        item
        for item in (normalize_row(row, spec) for row in raw)
        if matches_query(item, q) and in_date_range(item, spec, date_from, date_to)
    ]
    return {
        "slug": spec.slug,
        "title": spec.title,
        "subtitle": spec.subtitle,
        "kind": spec.kind,
        "columns": spec.columns,
        "rows": rows,
        "count": len(rows),
        "ocs_count": total,
        "summary": summarize(rows, spec),
        "filters": {"q": q, "date_from": date_from, "date_to": date_to, "page": page, "limit": limit},
        "ocs": client.health(),
    }


@app.get("/api/reports")
def report_index(user: str = Depends(current_user)) -> dict[str, Any]:
    return {"rows": menu_items()}


@app.get("/api/reports/{slug}.csv")
def report_csv(
    slug: str,
    user: str = Depends(current_user),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(1000, ge=1, le=1000),
) -> Response:
    spec = REPORTS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    data = _build_report(slug, q, date_from, date_to, page, limit)
    return Response(
        content=csv_text(data["rows"], spec),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{spec.filename}"'},
    )


@app.get("/api/reports/{slug}")
def report_view(
    slug: str,
    user: str = Depends(current_user),
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    return _build_report(slug, q, date_from, date_to, page, limit)


@app.get("/api/sip-devices")
def sip_devices(user: str = Depends(current_user)) -> dict[str, Any]:
    result = collect_sip_monitor(ocs())
    result["ocs"] = ocs().health()
    return result


@app.get("/api/invoices")
def invoices(user: str = Depends(current_user)) -> dict[str, Any]:
    return {"rows": store().list_invoices()}


@app.post("/api/invoices")
def create_invoice(payload: InvoiceIn, user: str = Depends(current_user)) -> dict[str, Any]:
    users = _rows(ocs().read("user", page=1, limit=500))
    target = next((row for row in users if int(row["id"]) == payload.ocs_user_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Customer not found in OCS")
    ocs().clear_filter()
    ocs().set_filter("id_user", payload.ocs_user_id, "eq", "numeric")
    try:
        calls = _rows(ocs().read("call", page=1, limit=500))
    finally:
        ocs().clear_filter()
    amount = round(sum(float(row.get("sessionbill") or 0) for row in calls), 4)
    invoice = store().add_invoice(
        {
            "ocs_user_id": payload.ocs_user_id,
            "username": target.get("username"),
            "period": payload.period,
            "amount": amount,
            "status": "open",
            "usage": calls[:100],
        }
    )
    return invoice


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


@app.exception_handler(OcsError)
async def ocs_handler(request: Request, exc: OcsError) -> JSONResponse:
    return JSONResponse({"detail": str(exc), "ocs": exc.payload}, status_code=502)
