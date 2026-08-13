"""BSS report catalog over MagnusBilling CDR and summary modules."""
from __future__ import annotations

from dataclasses import dataclass, field
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

CDR_COLUMNS = [
    {"key": "starttime", "label": "Started"},
    {"key": "username", "label": "User"},
    {"key": "src", "label": "Source"},
    {"key": "callerid", "label": "Caller ID"},
    {"key": "destination", "label": "Destination"},
    {"key": "prefix", "label": "Prefix"},
    {"key": "duration", "label": "Duration"},
    {"key": "billed", "label": "Billed", "format": "money"},
    {"key": "buy_cost", "label": "Buy", "format": "money"},
    {"key": "margin", "label": "Margin", "format": "money"},
    {"key": "terminate_cause", "label": "Cause", "format": "cause"},
]

FAILED_COLUMNS = [
    {"key": "starttime", "label": "Started"},
    {"key": "username", "label": "User"},
    {"key": "src", "label": "Source"},
    {"key": "callerid", "label": "Caller ID"},
    {"key": "destination", "label": "Destination"},
    {"key": "prefix", "label": "Prefix"},
    {"key": "plan", "label": "Plan"},
    {"key": "trunk", "label": "Trunk"},
    {"key": "terminate_cause", "label": "Cause", "format": "cause"},
    {"key": "hangup_cause", "label": "Hangup"},
]

SUMMARY_BASE = [
    {"key": "calls", "label": "Calls", "format": "int"},
    {"key": "failed_calls", "label": "Failed", "format": "int"},
    {"key": "asr", "label": "ASR %", "format": "pct"},
    {"key": "aloc_fmt", "label": "ALOC"},
    {"key": "duration", "label": "Duration"},
    {"key": "billed", "label": "Billed", "format": "money"},
    {"key": "buy_cost", "label": "Buy", "format": "money"},
    {"key": "margin", "label": "Margin", "format": "money"},
]


def _cols(*prefix: dict[str, str], extra: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    return list(prefix) + SUMMARY_BASE + list(extra or [])


@dataclass(frozen=True)
class ReportSpec:
    slug: str
    title: str
    subtitle: str
    module: str
    kind: str
    date_field: str
    columns: list[dict[str, str]] = field(default_factory=list)
    filename: str = ""


REPORTS: dict[str, ReportSpec] = {
    spec.slug: spec
    for spec in [
        ReportSpec(
            "cdr",
            "CDR",
            "Answered call detail records from the MagnusBilling OCS",
            "call",
            "cdr",
            "starttime",
            CDR_COLUMNS,
            "smartvoice-cdr.csv",
        ),
        ReportSpec(
            "cdr-failed",
            "CDR Failed",
            "Failed and unanswered attempts from the MagnusBilling OCS",
            "callFailed",
            "cdr-failed",
            "starttime",
            FAILED_COLUMNS,
            "smartvoice-cdr-failed.csv",
        ),
        ReportSpec(
            "summary-per-day",
            "Summary per Day",
            "Daily answered and failed call totals from the OCS",
            "callSummaryPerDay",
            "summary",
            "day",
            _cols({"key": "day", "label": "Day"}),
            "smartvoice-summary-per-day.csv",
        ),
        ReportSpec(
            "summary-day-user",
            "Summary Day User",
            "Daily call totals grouped by customer",
            "callSummaryDayUser",
            "summary",
            "day",
            _cols({"key": "day", "label": "Day"}, {"key": "username", "label": "User"}),
            "smartvoice-summary-day-user.csv",
        ),
        ReportSpec(
            "summary-day-trunk",
            "Summary Day Trunk",
            "Daily call totals grouped by trunk",
            "callSummaryDayTrunk",
            "summary",
            "day",
            _cols({"key": "day", "label": "Day"}, {"key": "trunk", "label": "Trunk"}),
            "smartvoice-summary-day-trunk.csv",
        ),
        ReportSpec(
            "summary-day-agent",
            "Summary Day Agent",
            "Daily call totals grouped by reseller or agent",
            "callSummaryDayAgent",
            "summary",
            "day",
            _cols(
                {"key": "day", "label": "Day"},
                {"key": "username", "label": "Agent"},
                extra=[{"key": "agent_bill", "label": "Agent billed", "format": "money"}],
            ),
            "smartvoice-summary-day-agent.csv",
        ),
        ReportSpec(
            "summary-per-month",
            "Summary per Month",
            "Monthly answered and failed call totals from the OCS",
            "callSummaryPerMonth",
            "summary",
            "month",
            _cols({"key": "month", "label": "Month"}),
            "smartvoice-summary-per-month.csv",
        ),
        ReportSpec(
            "summary-month-user",
            "Summary Month User",
            "Monthly call totals grouped by customer",
            "callSummaryMonthUser",
            "summary",
            "month",
            _cols({"key": "month", "label": "Month"}, {"key": "username", "label": "User"}),
            "smartvoice-summary-month-user.csv",
        ),
        ReportSpec(
            "summary-month-trunk",
            "Summary Month Trunk",
            "Monthly call totals grouped by trunk",
            "callSummaryMonthTrunk",
            "summary",
            "month",
            _cols({"key": "month", "label": "Month"}, {"key": "trunk", "label": "Trunk"}),
            "smartvoice-summary-month-trunk.csv",
        ),
        ReportSpec(
            "summary-per-user",
            "Summary per User",
            "Lifetime call totals grouped by customer",
            "callSummaryPerUser",
            "summary",
            "",
            _cols({"key": "username", "label": "User"}),
            "smartvoice-summary-per-user.csv",
        ),
        ReportSpec(
            "summary-per-trunk",
            "Summary per Trunk",
            "Lifetime call totals grouped by trunk",
            "callSummaryPerTrunk",
            "summary",
            "",
            _cols({"key": "trunk", "label": "Trunk"}),
            "smartvoice-summary-per-trunk.csv",
        ),
        ReportSpec(
            "call-archive",
            "Call Archive",
            "Archived call detail records from the MagnusBilling OCS",
            "callArchive",
            "cdr",
            "starttime",
            CDR_COLUMNS,
            "smartvoice-call-archive.csv",
        ),
        ReportSpec(
            "summary-month-did",
            "Summary Month DID",
            "Monthly inbound totals grouped by DID",
            "callSummaryMonthDid",
            "summary",
            "month",
            [
                {"key": "month", "label": "Month"},
                {"key": "did", "label": "DID"},
                {"key": "calls", "label": "Calls", "format": "int"},
                {"key": "aloc_fmt", "label": "ALOC"},
                {"key": "duration", "label": "Duration"},
                {"key": "billed", "label": "Billed", "format": "money"},
            ],
            "smartvoice-summary-month-did.csv",
        ),
    ]
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


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def matches_query(row: dict[str, Any], query: str) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    hay = " ".join(str(value) for value in row.values() if value not in (None, "")).lower()
    return needle in hay


def bound_dates(date_from: str, date_to: str) -> tuple[str, str]:
    start = (date_from or "").strip()
    end = (date_to or "").strip()
    if start and len(start) == 10:
        start = start + " 00:00:00"
    if end and len(end) == 10:
        end = end + " 23:59:59"
    return start, end


def in_date_range(row: dict[str, Any], spec: ReportSpec, date_from: str, date_to: str) -> bool:
    start, end = bound_dates(date_from, date_to)
    if not spec.date_field or (not start and not end):
        return True
    value = str(
        row.get(spec.date_field)
        or row.get("day")
        or row.get("month")
        or row.get("starttime")
        or ""
    )
    if spec.date_field == "month":
        if start and value[:7] < start[:7]:
            return False
        if end and value[:7] > end[:7]:
            return False
        return True
    if spec.date_field == "day":
        if start and value[:10] < start[:10]:
            return False
        if end and value[:10] > end[:10]:
            return False
        return True
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def normalize_cdr(row: dict[str, Any], failed: bool = False) -> dict[str, Any]:
    billed = _num(row.get("sessionbill"))
    buy = _num(row.get("buycost"))
    cause_id = row.get("terminatecauseid")
    hangup_id = row.get("hangupcause")
    return {
        "id": row.get("id"),
        "starttime": row.get("starttime") or "",
        "stoptime": row.get("stoptime") or "",
        "username": _first(row, "idUserusername", "id_user"),
        "src": row.get("src") or "",
        "callerid": row.get("callerid") or "",
        "destination": row.get("calledstation") or "",
        "prefix": row.get("idPrefixdestination") or "",
        "plan": row.get("idPlanname") or "",
        "trunk": _first(row, "idTrunktrunkcode", "id_trunk"),
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
        "calls": 1,
        "failed_calls": 1 if failed else 0,
    }


def normalize_summary(row: dict[str, Any]) -> dict[str, Any]:
    minutes = _num(row.get("sessiontime"))
    billed = _num(row.get("sessionbill"))
    buy = _num(row.get("buycost"))
    lucro = row.get("lucro")
    margin = _num(lucro) if lucro not in (None, "") else billed - buy
    seconds = int(round(minutes * 60)) if minutes and minutes < 100000 else int(minutes)
    # Summary APIs return sessiontime in minutes; raw tables can be seconds.
    if minutes >= 1000:
        seconds = int(minutes)
        minutes = seconds / 60.0
    return {
        "id": row.get("id"),
        "day": row.get("day") or "",
        "month": row.get("month") or "",
        "username": _first(row, "idUserusername", "id_user"),
        "trunk": _first(row, "idTrunktrunkcode", "id_trunk"),
        "did": _first(row, "idDiddid", "id_did"),
        "calls": int(_num(row.get("nbcall"))),
        "failed_calls": int(_num(row.get("nbcall_fail"))),
        "asr": round(_num(row.get("asr")), 2),
        "aloc": int(_num(row.get("aloc_all_calls"))),
        "aloc_fmt": format_duration(row.get("aloc_all_calls")),
        "session_minutes": round(minutes, 4),
        "duration_seconds": seconds,
        "duration": format_duration(seconds),
        "billed": round(billed, 6),
        "buy_cost": round(buy, 6),
        "margin": round(margin, 6),
        "agent_bill": round(_num(row.get("agent_bill")), 6),
        "agent_margin": round(_num(row.get("agent_lucro")), 6),
        "failed": False,
    }


def normalize_row(row: dict[str, Any], spec: ReportSpec) -> dict[str, Any]:
    if spec.kind == "summary":
        return normalize_summary(row)
    return normalize_cdr(row, failed=spec.kind == "cdr-failed")


def summarize(rows: list[dict[str, Any]], spec: ReportSpec) -> dict[str, Any]:
    billed = round(sum(_num(row.get("billed")) for row in rows), 6)
    buy = round(sum(_num(row.get("buy_cost")) for row in rows), 6)
    duration = sum(int(row.get("duration_seconds") or 0) for row in rows)
    calls = sum(int(row.get("calls") or 0) for row in rows)
    failed_calls = sum(int(row.get("failed_calls") or 0) for row in rows)
    asr = round((calls / (calls + failed_calls) * 100) if (calls + failed_calls) else 0, 2)
    causes: dict[str, int] = {}
    if spec.kind != "summary":
        for row in rows:
            label = str(row.get("hangup_cause") or row.get("terminate_cause") or "Unknown")
            causes[label] = causes.get(label, 0) + 1
    top_causes = sorted(causes.items(), key=lambda item: item[1], reverse=True)[:6]
    return {
        "count": len(rows),
        "calls": calls,
        "failed_calls": failed_calls,
        "asr": asr,
        "billed": billed,
        "buy_cost": buy,
        "margin": round(billed - buy, 6),
        "duration_seconds": duration,
        "duration": format_duration(duration),
        "answered": 0 if spec.kind == "cdr-failed" else sum(1 for row in rows if int(row.get("terminatecauseid") or 0) == 1) if spec.kind != "summary" else calls,
        "top_causes": [{"label": label, "count": count} for label, count in top_causes],
    }


def csv_text(rows: list[dict[str, Any]], spec: ReportSpec) -> str:
    headers = [col["key"] for col in spec.columns]
    lines = [",".join(headers)]
    for row in rows:
        cells = []
        for key in headers:
            value = str(row.get(key) if row.get(key) is not None else "")
            if any(ch in value for ch in ",\"\n"):
                value = '"' + value.replace('"', '""') + '"'
            cells.append(value)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def menu_items() -> list[dict[str, str]]:
    return [{"slug": spec.slug, "title": spec.title, "subtitle": spec.subtitle} for spec in REPORTS.values()]
