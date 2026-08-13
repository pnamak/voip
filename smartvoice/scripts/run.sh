#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/..:${PYTHONPATH:-}"
export SMARTVOICE_OCS_MOCK="${SMARTVOICE_OCS_MOCK:-1}"
exec python3 -m uvicorn smartvoice.app.main:app --app-dir "${ROOT}/.." --host "${SMARTVOICE_HOST:-127.0.0.1}" --port "${SMARTVOICE_PORT:-8088}"
