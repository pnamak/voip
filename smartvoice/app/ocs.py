"""MagnusBilling Online Charging System client.

Matches the official MagnusBilling API HMAC (PHP http_build_query + SHA-512).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from . import config


class OcsError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


class MagnusBillingOcs:
    """Live OCS adapter for MagnusBilling 8."""

    def __init__(
        self,
        public_url: str,
        api_key: str,
        api_secret: str,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.public_url = public_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.filter: list[dict[str, Any]] = []
        self.client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def query(self, req: dict[str, Any]) -> Any:
        payload = dict(req)
        mt = time.time()
        frac = f"{mt:.6f}".split(".")[1]
        payload["nonce"] = f"{int(mt)}{frac}"
        post_data = urlencode(payload, doseq=True)
        sign = hmac.new(
            self.api_secret.encode("utf-8"),
            post_data.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        module = payload.get("module") or "user"
        action = payload.get("action") or "read"
        url = f"{self.public_url}/index.php/{module}/{action}"
        headers = {
            "Key": self.api_key,
            "Sign": sign,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "SmartVoice-BSS/1.0",
        }
        response = self.client.post(url, content=post_data, headers=headers)
        if response.status_code != 200:
            raise OcsError(f"OCS HTTP {response.status_code}", response.text[:500])
        text = response.text.strip()
        if not text:
            raise OcsError("OCS returned an empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OcsError("OCS returned non-JSON", text[:500]) from exc

    def create(self, module: str, data: dict[str, Any] | None = None, action: str = "save") -> Any:
        body = dict(data or {})
        body.update({"module": module, "action": action, "id": 0})
        return self.query(body)

    def update(self, module: str, item_id: int | str, data: dict[str, Any]) -> Any:
        body = dict(data)
        body.update({"module": module, "action": "save", "id": item_id})
        return self.query(body)

    def destroy(self, module: str, item_id: int | str) -> Any:
        return self.query({"module": module, "action": "destroy", "id": item_id})

    def read(self, module: str, page: int = 1, limit: int = 25, action: str = "read") -> Any:
        start = 0 if page <= 1 else (page - 1) * limit
        return self.query(
            {
                "module": module,
                "action": action,
                "page": page,
                "start": start,
                "limit": limit,
                "filter": json.dumps(self.filter, separators=(",", ":")),
            }
        )

    def create_user(self, data: dict[str, Any]) -> Any:
        body = dict(data)
        body.update({"module": "user", "action": "save", "createUser": 1, "id": 0})
        return self.query(body)

    def set_filter(self, field: str, value: Any, comparison: str = "eq", type_: str = "string") -> None:
        self.filter.append(
            {"type": type_, "field": field, "value": value, "comparison": comparison}
        )

    def clear_filter(self) -> None:
        self.filter = []

    def health(self) -> dict[str, Any]:
        try:
            result = self.read("user", page=1, limit=1)
            ok = isinstance(result, dict) and "rows" in result
            return {
                "ok": ok,
                "engine": config.OCS_NAME,
                "mode": "live",
                "url": self.public_url,
                "detail": "Online charging API reachable" if ok else "Unexpected OCS payload",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "engine": config.OCS_NAME,
                "mode": "live",
                "url": self.public_url,
                "detail": str(exc),
            }


class MockOcs:
    """In-process OCS used for tests and when MagnusBilling is not configured."""

    def __init__(self) -> None:
        self.filter: list[dict[str, Any]] = []
        self._users = [
            {
                "id": 1,
                "username": "root",
                "firstname": "Platform",
                "lastname": "Admin",
                "email": "support@smartvoip.local",
                "credit": 0,
                "id_group": 1,
                "idGroupname": "Administrator",
                "id_plan": 1,
                "idPlanname": "SmartVoice Default",
                "id_user": None,
                "typepaid": 0,
                "active": 1,
                "company_name": "SmartVoice",
                "creditlimit": 0,
            },
            {
                "id": 10,
                "username": "pacific",
                "firstname": "Pacific",
                "lastname": "Resale",
                "email": "reseller@pacific.example",
                "credit": 250.0,
                "id_group": 2,
                "idGroupname": "Agent",
                "id_plan": 1,
                "idPlanname": "SmartVoice Default",
                "id_user": 1,
                "typepaid": 1,
                "active": 1,
                "company_name": "Pacific Voice",
                "creditlimit": 500,
            },
            {
                "id": 21,
                "username": "alice",
                "firstname": "Alice",
                "lastname": "Tari",
                "email": "alice@example.com",
                "credit": 18.4,
                "id_group": 3,
                "idGroupname": "Client",
                "id_plan": 1,
                "idPlanname": "SmartVoice Default",
                "id_user": 10,
                "typepaid": 0,
                "active": 1,
                "company_name": "Tari Shop",
                "creditlimit": 0,
            },
            {
                "id": 22,
                "username": "bobpost",
                "firstname": "Bob",
                "lastname": "Kalsong",
                "email": "bob@example.com",
                "credit": -12.5,
                "id_group": 3,
                "idGroupname": "Client",
                "id_plan": 2,
                "idPlanname": "Office Trunk",
                "id_user": 1,
                "typepaid": 1,
                "active": 1,
                "company_name": "Kalsong Ltd",
                "creditlimit": 100,
            },
        ]
        self._plans = [
            {"id": 1, "name": "SmartVoice Default", "ini_credit": 5, "signup": 1, "lcrtype": 0},
            {"id": 2, "name": "Office Trunk", "ini_credit": 0, "signup": 0, "lcrtype": 1},
        ]
        self._refills = [
            {
                "id": 1,
                "id_user": 21,
                "credit": 20,
                "payment": 1,
                "description": "Cash refill",
                "date": "2026-08-12 09:00:00",
                "idUserusername": "alice",
            }
        ]
        self._calls = [
            {
                "id": 1,
                "id_user": 21,
                "idUserusername": "alice",
                "calledstation": "67812345",
                "sessiontime": 73,
                "sessionbill": 0.41,
                "starttime": "2026-08-13 04:12:01",
                "terminatecauseid": 1,
                "src": "alice",
                "callerid": "Alice Tari",
                "buycost": 0.12,
                "real_sessiontime": 73,
                "idPlanname": "SmartVoice Default",
                "idPrefixdestination": "Vanuatu mobile",
                "idTrunktrunkcode": "Pacific-Out",
                "uniqueid": "mock-cdr-1",
            },
            {
                "id": 2,
                "id_user": 22,
                "idUserusername": "bobpost",
                "calledstation": "67855501",
                "sessiontime": 240,
                "sessionbill": 1.15,
                "starttime": "2026-08-13 05:40:00",
                "terminatecauseid": 1,
                "src": "bobpost",
                "callerid": "Bob Kalsong",
                "buycost": 0.40,
                "real_sessiontime": 240,
                "idPlanname": "Office Trunk",
                "idPrefixdestination": "Vanuatu",
                "idTrunktrunkcode": "Pacific-Out",
                "uniqueid": "mock-cdr-2",
            },
        ]
        self._failed = [
            {
                "id": 1,
                "id_user": 21,
                "idUserusername": "alice",
                "src": "alice",
                "callerid": "Alice Tari",
                "calledstation": "67899999",
                "starttime": "2026-08-13 04:15:22",
                "terminatecauseid": 3,
                "hangupcause": 19,
                "idPlanname": "SmartVoice Default",
                "idPrefixdestination": "Vanuatu mobile",
                "idTrunktrunkcode": "Pacific-Out",
                "uniqueid": "mock-fail-1",
            },
            {
                "id": 2,
                "id_user": 22,
                "idUserusername": "bobpost",
                "src": "bobpost",
                "callerid": "Bob Kalsong",
                "calledstation": "0015550100",
                "starttime": "2026-08-13 05:41:10",
                "terminatecauseid": 2,
                "hangupcause": 17,
                "idPlanname": "Office Trunk",
                "idPrefixdestination": "International",
                "idTrunktrunkcode": "Pacific-Out",
                "uniqueid": "mock-fail-2",
            },
            {
                "id": 3,
                "id_user": 21,
                "idUserusername": "alice",
                "src": "DID Call",
                "callerid": "alice",
                "calledstation": "2001",
                "starttime": "2026-08-13 05:50:00",
                "terminatecauseid": 6,
                "hangupcause": 20,
                "idPlanname": "SmartVoice Default",
                "idPrefixdestination": "Extensions",
                "idTrunktrunkcode": "",
                "uniqueid": "mock-fail-3",
            },
        ]
        self._online = [
            {
                "id": 1,
                "sip_account": "alice",
                "id_user": 21,
                "ndiscado": "67812345",
                "status": "answered",
                "duration": 42,
                "from_ip": "203.0.113.10",
                "canal": "PJSIP/alice-00000001",
            }
        ]
        self._sip = [
            {
                "id": 1,
                "id_user": 21,
                "name": "alice",
                "defaultuser": "alice",
                "accountcode": "alice",
                "idUserusername": "alice",
                "callerid": "Alice Tari",
                "cid_number": "Alice Tari",
                "host": "dynamic",
                "status": 1,
                "allow": "alaw,ulaw,g729",
                "lineStatus": "OK (12 ms) localhost",
                "secret": "should-not-leak",
                "useragent": "Zoiper",
                "fullcontact": "sip:alice@203.0.113.10:5060",
            },
            {
                "id": 2,
                "id_user": 22,
                "name": "bobpost",
                "defaultuser": "bobpost",
                "accountcode": "bobpost",
                "idUserusername": "bobpost",
                "callerid": "Bob Kalsong",
                "cid_number": "Bob Kalsong",
                "host": "dynamic",
                "status": 1,
                "allow": "alaw,ulaw",
                "lineStatus": "unregistered",
                "secret": "should-not-leak",
                "useragent": "",
                "fullcontact": "",
            },
            {
                "id": 3,
                "id_user": 10,
                "name": "pacific-shop",
                "defaultuser": "pacific-shop",
                "accountcode": "pacific",
                "idUserusername": "pacific",
                "callerid": "Pacific Shop",
                "host": "dynamic",
                "status": 0,
                "allow": "alaw,ulaw",
                "lineStatus": "unregistered",
                "secret": "should-not-leak",
            },
        ]
        self._next_user = 30
        self._next_plan = 3
        self._next_refill = 2

    def close(self) -> None:
        return None

    def set_filter(self, field: str, value: Any, comparison: str = "eq", type_: str = "string") -> None:
        self.filter.append(
            {"type": type_, "field": field, "value": value, "comparison": comparison}
        )

    def clear_filter(self) -> None:
        self.filter = []

    def _apply_filter(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = rows
        for item in self.filter:
            field = item["field"]
            value = item["value"]
            comparison = item.get("comparison", "eq")
            kept = []
            for row in result:
                current = row.get(field)
                if comparison == "eq" and str(current) == str(value):
                    kept.append(row)
                elif comparison == "st" and str(value).lower() in str(current or "").lower():
                    kept.append(row)
                elif comparison in {"gt", "lt"}:
                    try:
                        left = float(current or 0)
                        right = float(value)
                        if comparison == "gt" and left > right:
                            kept.append(row)
                        elif comparison == "lt" and left < right:
                            kept.append(row)
                    except (TypeError, ValueError):
                        left = str(current or "")
                        right = str(value)
                        if comparison == "gt" and left > right:
                            kept.append(row)
                        elif comparison == "lt" and left < right:
                            kept.append(row)
            result = kept
        return result

    def read(self, module: str, page: int = 1, limit: int = 25, action: str = "read") -> Any:
        table = {
            "user": self._users,
            "plan": self._plans,
            "refill": self._refills,
            "call": self._calls,
            "callOnLine": self._online,
            "sip": self._sip,
            "callFailed": self._failed,
        }.get(module, [])
        rows = self._apply_filter(list(table))
        start = 0 if page <= 1 else (page - 1) * limit
        return {"rows": rows[start : start + limit], "count": len(rows), "sum": []}

    def create(self, module: str, data: dict[str, Any] | None = None, action: str = "save") -> Any:
        body = dict(data or {})
        if module == "plan":
            item = {
                "id": self._next_plan,
                "name": body.get("name", "New plan"),
                "ini_credit": float(body.get("ini_credit") or 0),
                "signup": int(body.get("signup") or 0),
                "lcrtype": int(body.get("lcrtype") or 0),
            }
            self._next_plan += 1
            self._plans.append(item)
            return {"success": True, "rows": [item]}
        if module == "refill":
            item = {
                "id": self._next_refill,
                "id_user": int(body["id_user"]),
                "credit": float(body.get("credit") or 0),
                "payment": int(body.get("payment") or 1),
                "description": body.get("description", "BSS payment"),
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._next_refill += 1
            self._refills.append(item)
            for user in self._users:
                if int(user["id"]) == int(body["id_user"]):
                    user["credit"] = float(user.get("credit") or 0) + float(item["credit"])
                    item["idUserusername"] = user["username"]
                    break
            return {"success": True, "rows": [item]}
        return {"success": False, "errors": f"Unsupported mock create for {module}"}

    def update(self, module: str, item_id: int | str, data: dict[str, Any]) -> Any:
        table = {"user": self._users, "plan": self._plans}.get(module, [])
        for row in table:
            if str(row["id"]) == str(item_id):
                row.update({k: v for k, v in data.items() if k not in {"module", "action", "id"}})
                return {"success": True, "rows": [row]}
        return {"success": False, "errors": "Not found"}

    def destroy(self, module: str, item_id: int | str) -> Any:
        return {"success": True}

    def create_user(self, data: dict[str, Any]) -> Any:
        item = {
            "id": self._next_user,
            "username": data.get("username") or f"user{self._next_user}",
            "firstname": data.get("firstname", ""),
            "lastname": data.get("lastname", ""),
            "email": data.get("email", ""),
            "credit": float(data.get("credit") or 0),
            "id_group": int(data.get("id_group") or config.CLIENT_GROUP_ID),
            "idGroupname": "Agent" if int(data.get("id_group") or 3) == 2 else "Client",
            "id_plan": int(data.get("id_plan") or 1),
            "idPlanname": next((p["name"] for p in self._plans if p["id"] == int(data.get("id_plan") or 1)), ""),
            "id_user": int(data.get("id_user") or 1),
            "typepaid": int(data.get("typepaid") or 0),
            "active": int(data.get("active") or 1),
            "company_name": data.get("company_name", ""),
            "creditlimit": float(data.get("creditlimit") or 0),
        }
        self._next_user += 1
        self._users.append(item)
        return {"success": True, "data": item}

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "engine": config.OCS_NAME,
            "mode": "mock",
            "url": "mock://ocs",
            "detail": "Using in-process OCS simulator",
        }


def get_ocs() -> MagnusBillingOcs | MockOcs:
    if config.ocs_enabled():
        return MagnusBillingOcs(config.OCS_URL, config.OCS_KEY, config.OCS_SECRET, config.OCS_TIMEOUT)
    return MockOcs()
