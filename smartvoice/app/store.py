from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from . import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS operators (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    ocs_user_id INTEGER PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    ocs_plan_id INTEGER,
    monthly_fee REAL NOT NULL DEFAULT 0,
    included_minutes INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'voice'
);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ocs_user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    period TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    usage_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ocs_user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    amount REAL NOT NULL,
    method TEXT NOT NULL,
    reference TEXT NOT NULL,
    ocs_refill_id INTEGER,
    created_at TEXT NOT NULL
);
"""


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return secrets.compare_digest(check, digest)


class BssStore:
    def __init__(self, path: Path | None = None):
        config.data_dir().mkdir(parents=True, exist_ok=True)
        self.path = path or (config.data_dir() / "smartvoice.sqlite")
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            row = conn.execute(
                "SELECT username FROM operators WHERE username = ?", (config.ADMIN_USER,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO operators(username, password_hash, created_at) VALUES (?, ?, ?)",
                    (config.ADMIN_USER, _hash_password(config.admin_password()), time.strftime("%Y-%m-%d %H:%M:%S")),
                )
            if conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0:
                conn.executemany(
                    """INSERT INTO products(name, description, ocs_plan_id, monthly_fee, included_minutes, kind)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            "Prepaid Voice",
                            "Pay-as-you-go minutes charged in real time by the OCS",
                            1,
                            0,
                            0,
                            "prepaid",
                        ),
                        (
                            "Office Trunk",
                            "Postpaid SIP trunk with a credit limit enforced by the OCS",
                            2,
                            49,
                            1000,
                            "postpaid",
                        ),
                    ],
                )

    def authenticate(self, username: str, password: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM operators WHERE username = ?", (username,)
            ).fetchone()
        return bool(row) and verify_password(password, row["password_hash"])

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(token, username, created_at) VALUES (?, ?, ?)",
                (token, username, int(time.time())),
            )
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        max_age = 12 * 3600
        with self.connect() as conn:
            row = conn.execute(
                "SELECT username, created_at FROM sessions WHERE token = ?", (token,)
            ).fetchone()
            if not row:
                return None
            if int(time.time()) - int(row["created_at"]) > max_age:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
            return row["username"]

    def drop_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def get_note(self, ocs_user_id: int) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT note FROM notes WHERE ocs_user_id = ?", (ocs_user_id,)
            ).fetchone()
        return row["note"] if row else ""

    def set_note(self, ocs_user_id: int, note: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO notes(ocs_user_id, note, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(ocs_user_id) DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at""",
                (ocs_user_id, note, time.strftime("%Y-%m-%d %H:%M:%S")),
            )

    def list_products(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def add_product(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO products(name, description, ocs_plan_id, monthly_fee, included_minutes, kind)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    data["name"],
                    data.get("description", ""),
                    data.get("ocs_plan_id"),
                    float(data.get("monthly_fee") or 0),
                    int(data.get("included_minutes") or 0),
                    data.get("kind", "voice"),
                ),
            )
            item_id = cur.lastrowid
        return {"id": item_id, **data}

    def add_payment(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO payments(ocs_user_id, username, amount, method, reference, ocs_refill_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["ocs_user_id"],
                    data["username"],
                    float(data["amount"]),
                    data.get("method", "cash"),
                    data.get("reference", ""),
                    data.get("ocs_refill_id"),
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            item_id = cur.lastrowid
        return {"id": item_id, **data}

    def list_payments(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 200").fetchall()
        return [dict(row) for row in rows]

    def add_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """INSERT INTO invoices(ocs_user_id, username, period, amount, status, created_at, usage_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["ocs_user_id"],
                    data["username"],
                    data["period"],
                    float(data["amount"]),
                    data.get("status", "open"),
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    json.dumps(data.get("usage") or []),
                ),
            )
            item_id = cur.lastrowid
        return {"id": item_id, **data}

    def list_invoices(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM invoices ORDER BY id DESC LIMIT 200").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["usage"] = json.loads(item.pop("usage_json") or "[]")
            items.append(item)
        return items

    def mark_invoice(self, invoice_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))
