"""Normalize SIP device presence from MagnusBilling and Asterisk AMI."""
from __future__ import annotations

import re
import socket
import time
from typing import Any

from . import config

SECRET_FIELDS = {"secret", "md5secret", "sippasswd", "password"}
CONTACT_LINE = re.compile(r"^Contact:\s+", re.I)
ENDPOINT_LINE = re.compile(r"^Endpoint:\s+", re.I)
RTT_RE = re.compile(r"\((\d+)\s*ms\)", re.I)
URI_HOST_RE = re.compile(r"@([^;>\s]+)")


def classify_line_status(line_status: str | None) -> str:
    raw = (line_status or "").strip().lower()
    if not raw or raw.startswith("unregistered"):
        return "offline"
    if "unavail" in raw:
        return "unreachable"
    if raw.startswith("ok") or "avail" in raw:
        return "registered"
    if "not in use" in raw or "in use" in raw or raw.startswith("busy"):
        return "registered"
    return "unknown"


def extract_rtt_ms(line_status: str | None) -> int | None:
    match = RTT_RE.search(line_status or "")
    if not match:
        return None
    return int(match.group(1))


def parse_contact_host(uri: str | None) -> str:
    if not uri:
        return ""
    match = URI_HOST_RE.search(uri)
    return match.group(1) if match else ""


def parse_pjsip_contacts(output: str) -> dict[str, dict[str, Any]]:
    contacts: dict[str, dict[str, Any]] = {}
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not CONTACT_LINE.match(line):
            continue
        clean = CONTACT_LINE.sub("", line, count=1)
        parts = re.split(r"\s+", clean)
        if len(parts) < 3:
            continue
        aor_uri = parts[0]
        status = parts[2] if len(parts) > 2 else ""
        rtt_raw = parts[3] if len(parts) > 3 else ""
        aor, uri = (aor_uri.split("/", 1) + [""])[:2] if "/" in aor_uri else (aor_uri, "")
        rtt_ms = None
        try:
            rtt_ms = int(float(rtt_raw))
        except (TypeError, ValueError):
            rtt_ms = None
        contacts[aor] = {
            "aor": aor,
            "uri": uri,
            "contact": parse_contact_host(uri),
            "qualify": status,
            "rtt_ms": rtt_ms,
        }
    return contacts


def parse_pjsip_endpoints(output: str) -> dict[str, dict[str, Any]]:
    endpoints: dict[str, dict[str, Any]] = {}
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not ENDPOINT_LINE.match(line) or line.startswith("Endpoint:  <"):
            continue
        clean = ENDPOINT_LINE.sub("", line, count=1)
        parts = re.split(r"\s+", clean.strip())
        if len(parts) < 2:
            continue
        name = parts[0].split("/", 1)[0]
        state = " ".join(parts[1:-3]).strip() if len(parts) >= 4 else parts[1]
        channels = 0
        if len(parts) >= 3:
            try:
                channels = int(parts[-3])
            except ValueError:
                channels = 0
        endpoints[name] = {"name": name, "state": state or parts[1], "channels": channels}
    return endpoints


class AsteriskAmi:
    """Minimal AMI client for PJSIP show commands."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        secret: str,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.secret = secret
        self.timeout = timeout

    def command(self, cmd: str) -> str:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            self._login(sock)
            self._send(sock, {"Action": "Command", "Command": cmd, "ActionID": "sv1"})
            body = self._read_until(sock, "--END COMMAND--")
            self._send(sock, {"Action": "Logoff"})
        return body

    def contacts(self) -> dict[str, dict[str, Any]]:
        return parse_pjsip_contacts(self.command("pjsip show contacts"))

    def endpoints(self) -> dict[str, dict[str, Any]]:
        return parse_pjsip_endpoints(self.command("pjsip show endpoints"))

    def _login(self, sock: socket.socket) -> None:
        banner = self._read_until(sock, "\r\n")
        if "Asterisk Call Manager" not in banner:
            raise RuntimeError("Unexpected AMI banner")
        self._send(sock, {"Action": "Login", "Username": self.username, "Secret": self.secret, "Events": "off"})
        reply = self._read_until(sock, "\r\n\r\n")
        if "Success" not in reply:
            raise RuntimeError("AMI login failed")

    def _send(self, sock: socket.socket, fields: dict[str, str]) -> None:
        payload = "".join(f"{key}: {value}\r\n" for key, value in fields.items()) + "\r\n"
        sock.sendall(payload.encode("utf-8"))

    def _read_until(self, sock: socket.socket, marker: str) -> str:
        chunks = b""
        needle = marker.encode("utf-8")
        while needle not in chunks:
            piece = sock.recv(4096)
            if not piece:
                break
            chunks += piece
        return chunks.decode("utf-8", errors="replace")


def get_ami() -> AsteriskAmi | None:
    if not config.ami_enabled():
        return None
    return AsteriskAmi(
        config.AMI_HOST,
        config.AMI_PORT,
        config.AMI_USER,
        config.AMI_SECRET,
        config.AMI_TIMEOUT,
    )


def _live_by_sip(live_calls: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in live_calls:
        sip_account = str(row.get("sip_account") or "").strip()
        if sip_account:
            index[sip_account] = row
        canal = str(row.get("canal") or "")
        match = re.match(r"(?:PJSIP|SIP)/([^-/]+)", canal, re.I)
        if match:
            index[match.group(1)] = row
    return index


def _presence(row: dict[str, Any], live: dict[str, dict[str, Any]], endpoint: dict[str, Any] | None) -> str:
    name = str(row.get("name") or row.get("defaultuser") or "")
    if int(row.get("status") or 0) != 1:
        return "disabled"
    if name and name in live:
        return "in_call"
    if endpoint and int(endpoint.get("channels") or 0) > 0:
        return "in_call"
    return classify_line_status(row.get("lineStatus"))


def sanitize_sip_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in SECRET_FIELDS}


def monitor_sip_devices(
    sip_rows: list[dict[str, Any]],
    live_calls: list[dict[str, Any]] | None = None,
    contacts: dict[str, dict[str, Any]] | None = None,
    endpoints: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    live = _live_by_sip(live_calls or [])
    contacts = contacts or {}
    endpoints = endpoints or {}
    devices = []
    for raw in sip_rows:
        row = sanitize_sip_row(raw)
        name = str(row.get("name") or row.get("defaultuser") or "")
        contact = contacts.get(name) or contacts.get(str(row.get("host") or ""))
        endpoint = endpoints.get(name)
        call = live.get(name)
        presence = _presence(row, live, endpoint)
        rtt = extract_rtt_ms(row.get("lineStatus"))
        if contact and contact.get("rtt_ms") is not None:
            rtt = contact["rtt_ms"]
        devices.append(
            {
                "id": row.get("id"),
                "name": name,
                "customer": row.get("idUserusername") or row.get("accountcode") or "",
                "ocs_user_id": row.get("id_user"),
                "callerid": row.get("callerid") or row.get("cid_number") or "",
                "host": row.get("host") or "",
                "enabled": int(row.get("status") or 0) == 1,
                "presence": presence,
                "line_status": row.get("lineStatus") or "",
                "rtt_ms": rtt,
                "contact": (contact or {}).get("contact") or parse_contact_host(row.get("fullcontact")),
                "contact_uri": (contact or {}).get("uri") or row.get("fullcontact") or "",
                "user_agent": row.get("useragent") or "",
                "codecs": row.get("allow") or "",
                "call_limit": row.get("calllimit"),
                "in_call": presence == "in_call",
                "live_destination": (call or {}).get("ndiscado") or "",
                "live_duration": (call or {}).get("duration"),
                "live_status": (call or {}).get("status") or "",
                "endpoint_state": (endpoint or {}).get("state") or "",
                "channels": (endpoint or {}).get("channels") or 0,
            }
        )
    counts = {
        "total": len(devices),
        "registered": sum(1 for item in devices if item["presence"] in {"registered", "in_call"}),
        "offline": sum(1 for item in devices if item["presence"] == "offline"),
        "in_call": sum(1 for item in devices if item["presence"] == "in_call"),
        "unreachable": sum(1 for item in devices if item["presence"] == "unreachable"),
        "disabled": sum(1 for item in devices if item["presence"] == "disabled"),
    }
    return {"rows": devices, "count": len(devices), "counts": counts}


def collect_sip_monitor(ocs: Any) -> dict[str, Any]:
    sip_rows = []
    live_calls = []
    payload = ocs.read("sip", page=1, limit=500)
    if isinstance(payload, dict):
        sip_rows = list(payload.get("rows") or [])
    elif isinstance(payload, list):
        sip_rows = payload
    live_payload = ocs.read("callOnLine", page=1, limit=200)
    if isinstance(live_payload, dict):
        live_calls = list(live_payload.get("rows") or [])
    elif isinstance(live_payload, list):
        live_calls = live_payload
    contacts: dict[str, dict[str, Any]] = {}
    endpoints: dict[str, dict[str, Any]] = {}
    ami_ok = False
    ami_detail = "AMI not configured"
    ami = get_ami()
    if ami is not None:
        try:
            contacts = ami.contacts()
            endpoints = ami.endpoints()
            ami_ok = True
            ami_detail = f"Asterisk AMI {config.AMI_HOST}:{config.AMI_PORT}"
        except Exception as exc:  # noqa: BLE001
            ami_detail = str(exc)
    result = monitor_sip_devices(sip_rows, live_calls, contacts, endpoints)
    result["ami"] = {"ok": ami_ok, "detail": ami_detail}
    result["as_of"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return result
