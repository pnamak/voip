from __future__ import annotations

import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]


def data_dir() -> Path:
    return Path(os.environ.get("SMARTVOICE_DATA_DIR", str(APP_DIR.parent / "data")))
SECRET = os.environ.get("SMARTVOICE_SECRET", "smartvoice-dev-secret-change-me")
ADMIN_USER = os.environ.get("SMARTVOICE_ADMIN_USER", "admin")


def admin_password() -> str:
    return os.environ.get("SMARTVOICE_ADMIN_PASSWORD", "smartvoice")
BASE_PATH = os.environ.get("SMARTVOICE_BASE_PATH", "").rstrip("/")
HOST = os.environ.get("SMARTVOICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("SMARTVOICE_PORT", "8088"))

OCS_URL = os.environ.get("SMARTVOICE_OCS_URL", "http://127.0.0.1/mbilling").rstrip("/")
OCS_KEY = os.environ.get("SMARTVOICE_OCS_KEY", "")
OCS_SECRET = os.environ.get("SMARTVOICE_OCS_SECRET", "")
OCS_TIMEOUT = float(os.environ.get("SMARTVOICE_OCS_TIMEOUT", "20"))
FORCE_MOCK = _bool("SMARTVOICE_OCS_MOCK", False)

BRAND_NAME = "SmartVoice"
BRAND_PRODUCT = "SmartVoice BSS"
OCS_NAME = "MagnusBilling"
CLIENT_GROUP_ID = int(os.environ.get("SMARTVOICE_CLIENT_GROUP_ID", "3"))
RESELLER_GROUP_ID = int(os.environ.get("SMARTVOICE_RESELLER_GROUP_ID", "2"))


def ocs_enabled() -> bool:
    return (not FORCE_MOCK) and bool(OCS_KEY and OCS_SECRET and OCS_URL)
