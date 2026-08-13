#!/usr/bin/env python3
"""Destroy the SmartVoIP DigitalOcean droplet created by deploy.py."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.digitalocean.com/v2"
REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS = REPO_ROOT / ".secrets"


def token() -> str:
    value = os.environ.get("DIGITALOCEAN_TOKEN") or os.environ.get("DIGITALOCEAN_ACCESS_TOKEN")
    if not value:
        secret_file = SECRETS / "digitalocean.token"
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
    if not value:
        print("Set DIGITALOCEAN_TOKEN.", file=sys.stderr)
        raise SystemExit(1)
    return value


def api(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(errors="replace"), file=sys.stderr)
        raise


def main() -> None:
    name = os.environ.get("DO_DROPLET_NAME", "smartvoip-billing")
    deployment = SECRETS / "deployment.json"
    droplet_id = None
    if deployment.exists():
        droplet_id = json.loads(deployment.read_text(encoding="utf-8")).get("droplet_id")
    if droplet_id is None:
        droplets = api("GET", "/droplets?per_page=200").get("droplets", [])
        match = [d for d in droplets if d.get("name") == name]
        if not match:
            print(f"No droplet named {name} found.")
            return
        droplet_id = match[0]["id"]
    api("DELETE", f"/droplets/{droplet_id}")
    print(f"Deleted droplet id={droplet_id}")


if __name__ == "__main__":
    main()
