"""Blocked-IP monitoring from MagnusBilling firewall / Fail2ban."""
from __future__ import annotations

import ipaddress
from typing import Any

import httpx

from . import config

ACTION_LABELS = {
    0: "Temporary ban",
    1: "Permanent ban",
    3: "Unban pending",
    5: "Allow list",
}

JAIL_REASONS = {
    "asterisk-iptables": "Failed SIP / Asterisk authentication",
    "asterisk-manager": "Failed Asterisk Manager login",
    "sshd": "Failed SSH login",
    "mbilling_login": "Failed billing panel login",
    "mbilling_ddos": "HTTP flood against the billing panel",
    "ip-blacklist": "Listed on the IP blacklist",
    "ast-cli-attck": "Asterisk CLI attack",
    "ast-hgc-200": "Suspicious Asterisk hangup pattern",
    "IgnoreIP": "Allow-listed (not blocked)",
}

BLOCKED_ACTIONS = {0, 1}

MOCK_GEO = {
    "203.0.113.50": ("Germany", "DE"),
    "198.51.100.10": ("China", "CN"),
    "192.0.2.8": ("Private network", "ZZ"),
}


def action_label(value: Any) -> str:
    try:
        return ACTION_LABELS.get(int(value), f"Action {value}")
    except (TypeError, ValueError):
        return str(value or "Unknown")


def block_reason(jail: str | None, action: Any = 0) -> str:
    name = (jail or "").strip()
    reason = JAIL_REASONS.get(name, name.replace("-", " ").strip() or "Blocked by Fail2ban")
    try:
        code = int(action)
    except (TypeError, ValueError):
        code = 0
    if code == 1 and name != "IgnoreIP":
        return f"{reason} (permanent ban)"
    return reason


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("/")[0])
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)


def _lookup_live(ips: list[str]) -> dict[str, tuple[str, str]]:
    if not ips:
        return {}
    found: dict[str, tuple[str, str]] = {}
    try:
        payload = [{"query": ip} for ip in ips]
        with httpx.Client(timeout=6.0) as client:
            response = client.post(
                "http://ip-api.com/batch?fields=status,country,countryCode,query",
                json=payload,
            )
            response.raise_for_status()
            rows = response.json()
    except Exception:  # noqa: BLE001
        return found
    if not isinstance(rows, list):
        return found
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "success":
            continue
        query = str(row.get("query") or "")
        country = str(row.get("country") or "Unknown")
        code = str(row.get("countryCode") or "")
        if query:
            found[query] = (country, code)
    return found


def resolve_countries(ips: list[str], store: Any) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    unique = []
    seen = set()
    for ip in ips:
        if not ip or ip in seen:
            continue
        seen.add(ip)
        unique.append(ip)
    for ip in unique:
        if config.FORCE_MOCK:
            country, code = MOCK_GEO.get(ip, ("Testland", "TL"))
            result[ip] = {"country": country, "country_code": code}
            continue
        if _is_private(ip):
            result[ip] = {"country": "Private network", "country_code": "ZZ"}
            continue
        cached = store.get_geo(ip) if store is not None else None
        if cached:
            result[ip] = cached
        else:
            missing.append(ip)
    if missing:
        live = _lookup_live(missing)
        for ip in missing:
            country, code = live.get(ip, ("Unknown", ""))
            result[ip] = {"country": country, "country_code": code}
            if store is not None and country != "Unknown":
                store.set_geo(ip, country, code)
    return result


def collect_blocked_ips(ocs: Any, store: Any = None, q: str = "") -> dict[str, Any]:
    payload = ocs.read("firewall", page=1, limit=1000)
    raw = payload.get("rows") if isinstance(payload, dict) else payload
    if raw is False or raw is None:
        raw = []
    if not isinstance(raw, list):
        raw = []
    blocked = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            action = int(row.get("action") if row.get("action") is not None else -1)
        except (TypeError, ValueError):
            action = -1
        if action not in BLOCKED_ACTIONS:
            continue
        blocked.append(row)
    geo = resolve_countries([str(row.get("ip") or "") for row in blocked], store)
    needle = (q or "").strip().lower()
    rows = []
    countries: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for row in blocked:
        ip = str(row.get("ip") or "")
        loc = geo.get(ip) or {"country": "Unknown", "country_code": ""}
        jail = str(row.get("jail") or "")
        reason = block_reason(jail, row.get("action"))
        item = {
            "id": row.get("id"),
            "ip": ip,
            "country": loc["country"],
            "country_code": loc.get("country_code") or "",
            "reason": reason,
            "jail": jail,
            "action": action_label(action),
            "action_id": action,
            "date": row.get("date") or "",
            "server": row.get("idServername") or row.get("description") or "",
        }
        blob = " ".join(str(value) for value in item.values()).lower()
        if needle and needle not in blob:
            continue
        rows.append(item)
        countries[item["country"]] = countries.get(item["country"], 0) + 1
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {
        "rows": rows,
        "count": len(rows),
        "counts": {
            "total": len(rows),
            "temporary": sum(1 for row in rows if row.get("action_id") == 0),
            "permanent": sum(1 for row in rows if row.get("action_id") == 1),
        },
        "by_country": [{"label": label, "count": count} for label, count in sorted(countries.items(), key=lambda item: item[1], reverse=True)],
        "by_reason": [{"label": label, "count": count} for label, count in sorted(reasons.items(), key=lambda item: item[1], reverse=True)],
    }
