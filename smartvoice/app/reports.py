"""CDR and failed-CDR report helpers for the SmartVoice BSS."""
from __future__ import annotations

from typing import Any

TERMINATE_CAUSES = {
    0: "Unknown",
    1: "ANSWER",
    2: "BUSY",
    3: "NOANSWER",
    4: "CANCEL",
    5: "CONGESTION",
    6: "CHANUNAVAIL",
    7: "DONTCALL",
    8: "TORTURE",
    9: "INVALIDARGS",
}

HANGUP_CAUSES = {
    0: "Unspecified",
    1: "Unallocated number",
    16: "Normal clearing",
    17: "User busy",
    18: "No user responding",
    19: "No answer",
    20: "Subscriber absent",
    21: "Call rejected",
    27: "Destination out of order",
    28: "Invalid number format",
    31: "Normal, unspecified",
    34: "No circuit available",
    38: "Network out of order",
    41: "Temporary failure",
    42: "Switching congestion",
    47: "Resource unavailable",
    58: "Bearer cap. not available",
    88: "Incompatible destination",
    102: "Recovery on timer expiry",
}


def terminate_label(value: Any) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return str(value or "Unknown")
    return TERMINATE_CAUSES.get(code, f"Cause {code}")


def hangup_label(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return str(value)
    return HANGUP_CAUSES.get(code, f"Q.850 {code}")


def format_duration(seconds: Any) -> str:
    try:
        total = int(float(seconds or 0))
    except (TypeError, ValueError):
        return "0:00"
    hours, rem = divmod(max(total, 0), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def matches_query(row: dict[str, Any], query: str) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    hay = " ".join(
        str(row.get(key) or "")
        for key in (
            "idUserusername",
            "src",
            "callerid",
            "calledstation",
            "idPlanname",
            "idPrefixdestination",
            "idTrunktrunkcode",
            "uniqueid",
        )
    ).lower()
    return needle in hay


def normalize_cdr(row: dict[str, Any], failed: bool = False) -> dict[str, Any]:
    billed = _num(row.get("sessionbill"))
    buy = _num(row.get("buycost"))
    cause_id = row.get("terminatecauseid")
    hangup_id = row.get("hangupcause")
    item = {
        "id": row.get("id"),
        "starttime": row.get("starttime") or "",
        "username": row.get("idUserusername") or row.get("id_user") or "",
        "src": row.get("src") or "",
        "callerid": row.get("callerid") or "",
        "destination": row.get("calledstation") or "",
        "prefix": row.get("idPrefixdestination") or "",
        "plan": row.get("idPlanname") or "",
        "trunk": row.get("idTrunktrunkcode") or "",
        "duration_seconds": int(_num(row.get("sessiontime"))),
        "duration": format_duration(row.get("sessiontime")),
        "billed": round(billed, 6),
        "buy_cost": round(buy, 6),
        "margin": round(billed - buy, 6),
        "terminatecauseid": cause_id,
        "terminate_cause": terminate_label(cause_id),
        "hangupcause": hangup_id,
        "hangup_cause": hangup_label(hangup_id),
        "uniqueid": row.get("uniqueid") or "",
        "failed": failed,
    }
    return item


def summarize(rows: list[dict[str, Any]], failed: bool = False) -> dict[str, Any]:
    billed = round(sum(_num(row.get("billed")) for row in rows), 6)
    buy = round(sum(_num(row.get("buy_cost")) for row in rows), 6)
    duration = sum(int(row.get("duration_seconds") or 0) for row in rows)
    causes: dict[str, int] = {}
    for row in rows:
        label = str(row.get("hangup_cause") or row.get("terminate_cause") or "Unknown")
        causes[label] = causes.get(label, 0) + 1
    top_causes = sorted(causes.items(), key=lambda item: item[1], reverse=True)[:6]
    return {
        "count": len(rows),
        "billed": billed,
        "buy_cost": buy,
        "margin": round(billed - buy, 6),
        "duration_seconds": duration,
        "duration": format_duration(duration),
        "answered": 0 if failed else sum(1 for row in rows if int(row.get("terminatecauseid") or 0) == 1),
        "top_causes": [{"label": label, "count": count} for label, count in top_causes],
    }


def csv_text(rows: list[dict[str, Any]], failed: bool = False) -> str:
    if failed:
        headers = [
            "starttime",
            "username",
            "src",
            "callerid",
            "destination",
            "prefix",
            "plan",
            "trunk",
            "terminate_cause",
            "hangup_cause",
            "uniqueid",
        ]
    else:
        headers = [
            "starttime",
            "username",
            "src",
            "callerid",
            "destination",
            "prefix",
            "plan",
            "trunk",
            "duration",
            "billed",
            "buy_cost",
            "margin",
            "terminate_cause",
            "uniqueid",
        ]
    lines = [",".join(headers)]
    for row in rows:
        cells = []
        for key in headers:
            value = str(row.get(key) or "")
            if any(ch in value for ch in ",\"\n"):
                value = '"' + value.replace('"', '""') + '"'
            cells.append(value)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def bound_dates(date_from: str, date_to: str) -> tuple[str, str]:
    start = (date_from or "").strip()
    end = (date_to or "").strip()
    if start and len(start) == 10:
        start = start + " 00:00:00"
    if end and len(end) == 10:
        end = end + " 23:59:59"
    return start, end
