"""MagnusBilling-compatible user create helpers for the BSS."""
from __future__ import annotations

import re
import secrets
import string
from typing import Any

from fastapi import HTTPException

WEAK_PASSWORDS = {"123456", "12345678", "012345"}
USERNAME_RE = re.compile(r"^[0-9A-Za-z]\S{3,19}$")
LANGUAGES = ("en", "es", "pt_BR", "fr", "it")

# Fields MagnusBilling stores as empty string rather than NULL.
STRING_FIELDS = (
    "username",
    "password",
    "firstname",
    "lastname",
    "email",
    "email2",
    "company_name",
    "commercial_name",
    "company_website",
    "address",
    "city",
    "neighborhood",
    "state",
    "country",
    "zipcode",
    "phone",
    "mobile",
    "vat",
    "doc",
    "description",
    "prefix_local",
    "language",
)

INT_FIELDS = (
    "id_group",
    "id_plan",
    "id_user",
    "id_offer",
    "active",
    "typepaid",
    "creditlimit",
    "calllimit",
    "sipaccountlimit",
    "cpslimit",
    "inbound_call_limit",
    "restriction",
    "record_call",
    "callingcard_pin",
    "credit_notification",
)

OCS_FIELDS = STRING_FIELDS + INT_FIELDS + ("credit",)


def generate_username() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "u" + "".join(secrets.choice(alphabet) for _ in range(7))


def generate_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUWXYZabcdefghijkmnpqrstuvwxyz123456789"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(10))
        if password not in WEAK_PASSWORDS:
            return password


def validate_username(username: str) -> str:
    value = (username or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Username is required")
    if " " in value:
        raise HTTPException(status_code=400, detail="No space allow in username")
    if len(value) < 4 or len(value) > 20:
        raise HTTPException(status_code=400, detail="Username must be 4-20 characters")
    if not value[0].isalnum():
        raise HTTPException(status_code=400, detail="Username need start with numbers or letters")
    if not USERNAME_RE.match(value):
        raise HTTPException(status_code=400, detail="Invalid username")
    return value


def validate_password(password: str, username: str) -> str:
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    if " " in password:
        raise HTTPException(status_code=400, detail="No space allow in password")
    if password in WEAK_PASSWORDS:
        raise HTTPException(status_code=400, detail="No use sequence in the password")
    if password == username:
        raise HTTPException(status_code=400, detail="Password cannot be equal username")
    if len(password) > 100:
        raise HTTPException(status_code=400, detail="Password is too long")
    return password


def flatten_ocs_errors(errors: Any, fallback: str) -> str:
    if isinstance(errors, dict):
        parts = []
        for key, value in errors.items():
            if isinstance(value, list):
                parts.append(f"{key}: {'; '.join(str(item) for item in value)}")
            else:
                parts.append(f"{key}: {value}")
        return "; ".join(parts) or fallback
    if errors:
        return str(errors)
    return fallback


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def prepare_user_payload(
    payload: Any,
    *,
    id_group: int,
    default_plan_id: int | None = None,
    force_typepaid: int | None = None,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Build an OCS user save body from a BSS create payload.

    Returns (ocs_fields, bss_note, credentials).
    """
    raw = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    note = str(raw.pop("note", "") or "")
    username = str(raw.get("username") or "").strip() or generate_username()
    username = validate_username(username)
    password = str(raw.get("password") or "")
    if not password:
        password = generate_password()
    password = validate_password(password, username)

    email = str(raw.get("email") or "").strip()
    if not email:
        email = f"{username}@smartvoice.local"

    language = str(raw.get("language") or "en").strip() or "en"
    if language not in LANGUAGES:
        language = "en"

    data: dict[str, Any] = {
        "username": username,
        "password": password,
        "email": email,
        "language": language,
        "id_group": int(id_group),
        "id_user": _as_int(raw.get("id_user"), 1) or 1,
        "active": _as_int(raw.get("active"), 1),
        "typepaid": force_typepaid if force_typepaid is not None else _as_int(raw.get("typepaid"), 0),
        "credit": float(raw.get("credit") or 0),
        "creditlimit": _as_int(raw.get("creditlimit"), 0) or 0,
    }

    plan_id = _as_int(raw.get("id_plan"), default_plan_id)
    if plan_id is not None and plan_id > 0:
        data["id_plan"] = plan_id

    offer_id = _as_int(raw.get("id_offer"))
    if offer_id is not None and offer_id > 0:
        data["id_offer"] = offer_id

    pin = _as_int(raw.get("callingcard_pin"))
    if pin is not None and pin > 0:
        data["callingcard_pin"] = pin

    for key in STRING_FIELDS:
        if key in {"username", "password", "email", "language"}:
            continue
        value = raw.get(key)
        data[key] = "" if value is None else str(value).strip()

    for key, default in (
        ("calllimit", -1),
        ("sipaccountlimit", -1),
        ("cpslimit", -1),
        ("inbound_call_limit", -1),
        ("restriction", 0),
        ("record_call", 0),
        ("credit_notification", 10),
    ):
        data[key] = _as_int(raw.get(key), default)
        if data[key] is None:
            data[key] = default

    credentials = {"username": username, "password": password}
    return data, note, credentials


def prepare_user_update(
    payload: Any,
    existing: dict[str, Any],
    *,
    id_group: int,
    force_typepaid: int | None = None,
) -> tuple[dict[str, Any], str]:
    """Build an OCS user save body for an existing customer.

    Blank password is left unchanged. Returns (ocs_fields, bss_note).
    """
    raw = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
    note = str(raw["note"]) if "note" in raw else str(existing.get("bss_note") or existing.get("note") or "")
    username = str(raw.get("username") or existing.get("username") or "").strip()
    username = validate_username(username)

    data: dict[str, Any] = {
        "username": username,
        "id_group": int(id_group),
        "id_user": _as_int(raw.get("id_user"), _as_int(existing.get("id_user"), 1)) or 1,
        "active": _as_int(raw.get("active"), _as_int(existing.get("active"), 1)),
        "typepaid": force_typepaid
        if force_typepaid is not None
        else _as_int(raw.get("typepaid"), _as_int(existing.get("typepaid"), 0)),
        "credit": float(raw["credit"]) if "credit" in raw else float(existing.get("credit") or 0),
        "creditlimit": _as_int(raw.get("creditlimit"), _as_int(existing.get("creditlimit"), 0)) or 0,
    }

    password = str(raw.get("password") or "")
    if password:
        data["password"] = validate_password(password, username)

    email = str(raw.get("email") or "").strip()
    if not email:
        email = str(existing.get("email") or "").strip() or f"{username}@smartvoice.local"
    data["email"] = email

    language = str(raw.get("language") or existing.get("language") or "en").strip() or "en"
    if language not in LANGUAGES:
        language = "en"
    data["language"] = language

    plan_id = _as_int(raw.get("id_plan"), _as_int(existing.get("id_plan")))
    if plan_id is not None and plan_id > 0:
        data["id_plan"] = plan_id

    offer_id = _as_int(raw.get("id_offer"))
    if offer_id is not None and offer_id > 0:
        data["id_offer"] = offer_id

    pin = _as_int(raw.get("callingcard_pin"))
    if pin is not None and pin > 0:
        data["callingcard_pin"] = pin

    for key in STRING_FIELDS:
        if key in {"username", "password", "email", "language"}:
            continue
        if key in raw:
            data[key] = "" if raw[key] is None else str(raw[key]).strip()
        else:
            data[key] = str(existing.get(key) or "")

    for key, default in (
        ("calllimit", -1),
        ("sipaccountlimit", -1),
        ("cpslimit", -1),
        ("inbound_call_limit", -1),
        ("restriction", 0),
        ("record_call", 0),
        ("credit_notification", 10),
    ):
        data[key] = _as_int(raw.get(key), _as_int(existing.get(key), default))
        if data[key] is None:
            data[key] = default

    return data, note


BULK_USER_FIELDS = (
    "id_plan",
    "id_user",
    "active",
    "typepaid",
    "credit",
    "creditlimit",
    "language",
    "calllimit",
    "sipaccountlimit",
    "inbound_call_limit",
    "cpslimit",
    "restriction",
    "record_call",
    "prefix_local",
)


def prepare_bulk_fields(payload: Any) -> dict[str, Any]:
    raw = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)
    data: dict[str, Any] = {}
    for key in BULK_USER_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if key in STRING_FIELDS:
            data[key] = str(value).strip()
            if key == "language" and data[key] not in LANGUAGES:
                raise HTTPException(status_code=400, detail="Invalid language")
            continue
        if key == "credit":
            data[key] = float(value)
            continue
        number = _as_int(value)
        if number is None:
            continue
        if key == "id_plan" and number < 1:
            continue
        data[key] = number
    return data
