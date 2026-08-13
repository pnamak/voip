#!/usr/bin/env python3
"""Create a DigitalOcean Droplet running branded SmartVoIP / MagnusBilling."""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import string
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.digitalocean.com/v2"
REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS = REPO_ROOT / ".secrets"


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def token() -> str:
    value = os.environ.get("DIGITALOCEAN_TOKEN") or os.environ.get("DIGITALOCEAN_ACCESS_TOKEN")
    if not value:
        secret_file = SECRETS / "digitalocean.token"
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
    if not value:
        die("Set DIGITALOCEAN_TOKEN in the environment. Do not commit the token.")
    if value.startswith("dop_v1_replace"):
        die("Replace the placeholder token in .env before deploying.")
    return value


def api(method: str, path: str, body: dict | None = None, retries: int = 4):
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    delay = 4
    for attempt in range(retries):
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            err = exc.read().decode(errors="replace")
            if attempt + 1 == retries or exc.code in (400, 401, 403, 404, 422):
                die(f"DigitalOcean API {method} {path} failed ({exc.code}): {err[:2000]}")
            time.sleep(delay)
            delay *= 2
        except urllib.error.URLError as exc:
            if attempt + 1 == retries:
                die(f"DigitalOcean API {method} {path} network error: {exc}")
            time.sleep(delay)
            delay *= 2
    die(f"DigitalOcean API {method} {path} failed after retries.")


def random_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_ssh_key() -> tuple[int, Path]:
    SECRETS.mkdir(mode=0o700, exist_ok=True)
    key_path = SECRETS / "smartvoip_ed25519"
    pub_path = Path(str(key_path) + ".pub")
    if not pub_path.exists():
        subprocess.check_call(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(key_path),
                "-N",
                "",
                "-C",
                "smartvoip-deploy",
            ]
        )
        os.chmod(key_path, 0o600)
    public = pub_path.read_text(encoding="utf-8").strip()
    existing = api("GET", "/account/keys?per_page=200").get("ssh_keys", [])
    for key in existing:
        if key.get("public_key", "").strip() == public:
            return int(key["id"]), key_path
    created = api("POST", "/account/keys", {"name": "smartvoip-deploy", "public_key": public})
    return int(created["ssh_key"]["id"]), key_path


def branding_tarball() -> bytes:
    buf = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    buf.close()
    try:
        with tarfile.open(buf.name, "w:gz") as tar:
            for rel in (
                "branding",
                "deploy/digitalocean/bootstrap.sh",
            ):
                tar.add(REPO_ROOT / rel, arcname=rel)
        return Path(buf.name).read_bytes()
    finally:
        Path(buf.name).unlink(missing_ok=True)


def cloud_init(root_password: str, admin_password: str, branding_gz: bytes) -> str:
    bootstrap = (REPO_ROOT / "deploy/digitalocean/bootstrap.sh").read_text(encoding="utf-8")
    branding_b64 = base64.b64encode(branding_gz).decode()
    creds = f"""SmartVoIP credentials - change these after first login
Panel URL: http://SERVER_IP/
Panel path: /mbilling/
Username: root
Password: {admin_password}
SSH user: root
SSH password: {root_password}
Engine: MagnusBilling 8
"""
    branding_wrapped = "\n".join(
        branding_b64[i : i + 76] for i in range(0, len(branding_b64), 76)
    )
    return f"""#cloud-config
hostname: smartvoip-billing
manage_etc_hosts: true
package_update: true
ssh_pwauth: true
disable_root: false
chpasswd:
  expire: false
  list: |
    root:{root_password}
write_files:
  - path: /root/smartvoip-branding.tar.gz
    encoding: b64
    permissions: '0600'
    content: |
{chr(10).join('      ' + line for line in branding_wrapped.splitlines())}
  - path: /root/smartvoip-credentials.txt
    permissions: '0600'
    content: |
{chr(10).join('      ' + line if line else '      ' for line in creds.splitlines())}
  - path: /usr/local/sbin/smartvoip-bootstrap.sh
    permissions: '0700'
    content: |
{chr(10).join('      ' + line if line else '      ' for line in bootstrap.splitlines())}
  - path: /etc/systemd/system/smartvoip-bootstrap.service
    permissions: '0644'
    content: |
      [Unit]
      Description=SmartVoIP MagnusBilling bootstrap
      After=network-online.target
      Wants=network-online.target
      ConditionPathExists=!/var/lib/smartvoip/installed

      [Service]
      Type=oneshot
      Environment=SMARTVOIP_ADMIN_PASSWORD={admin_password}
      ExecStart=/usr/local/sbin/smartvoip-bootstrap.sh
      TimeoutStartSec=0
      RemainAfterExit=yes

      [Install]
      WantedBy=multi-user.target
runcmd:
  - [mkdir, -p, /var/www/html]
  - [bash, -lc, "echo '{{\\"status\\":\\"installing\\",\\"brand\\":\\"SmartVoIP\\"}}' > /var/www/html/install-status.json"]
  - [systemctl, daemon-reload]
  - [systemctl, enable, --now, smartvoip-bootstrap.service]
"""


def ensure_firewall(droplet_id: int) -> int:
    name = "smartvoip-billing"
    firewalls = api("GET", "/firewalls?per_page=200").get("firewalls", [])
    inbound = [
        {"protocol": "tcp", "ports": "22", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "tcp", "ports": "80", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "tcp", "ports": "443", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "tcp", "ports": "5060", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "udp", "ports": "5060", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "tcp", "ports": "5061", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "udp", "ports": "10000-20000", "sources": {"addresses": ["0.0.0.0/0", "::/0"]}},
    ]
    outbound = [
        {"protocol": "icmp", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "tcp", "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
        {"protocol": "udp", "ports": "all", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
    ]
    for fw in firewalls:
        if fw.get("name") == name:
            fw_id = fw["id"]
            api("POST", f"/firewalls/{fw_id}/droplets", {"droplet_ids": [droplet_id]})
            return fw_id
    created = api(
        "POST",
        "/firewalls",
        {
            "name": name,
            "inbound_rules": inbound,
            "outbound_rules": outbound,
            "droplet_ids": [droplet_id],
            "tags": ["smartvoip"],
        },
    )
    return created["firewall"]["id"]


def public_ip(droplet: dict) -> str | None:
    for net in droplet.get("networks", {}).get("v4", []):
        if net.get("type") == "public":
            return net.get("ip_address")
    return None


def wait_active(droplet_id: int, timeout: int = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        droplet = api("GET", f"/droplets/{droplet_id}")["droplet"]
        if droplet.get("status") == "active" and public_ip(droplet):
            return droplet
        time.sleep(8)
    die(f"Droplet {droplet_id} did not become active in time.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy SmartVoIP to DigitalOcean")
    parser.add_argument("--region", default=os.environ.get("DO_REGION", "syd1"))
    parser.add_argument("--size", default=os.environ.get("DO_SIZE", "s-2vcpu-4gb-amd"))
    parser.add_argument("--image", default=os.environ.get("DO_IMAGE", "debian-13-x64"))
    parser.add_argument("--name", default=os.environ.get("DO_DROPLET_NAME", "smartvoip-billing"))
    parser.add_argument("--wait-active", action="store_true", default=True)
    args = parser.parse_args()

    SECRETS.mkdir(mode=0o700, exist_ok=True)
    account = api("GET", "/account")["account"]
    print(f"Authenticated to DigitalOcean as {account.get('email')} (status={account.get('status')})")

    existing = api("GET", "/droplets?per_page=200").get("droplets", [])
    for droplet in existing:
        if droplet.get("name") == args.name:
            ip = public_ip(droplet) or "pending"
            print(f"Droplet {args.name} already exists as id={droplet['id']} ip={ip} status={droplet.get('status')}")
            (SECRETS / "deployment.json").write_text(
                json.dumps(
                    {
                        "droplet_id": droplet["id"],
                        "name": droplet["name"],
                        "ip": ip,
                        "region": droplet.get("region", {}).get("slug"),
                        "status": droplet.get("status"),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return

    ssh_id, key_path = ensure_ssh_key()
    root_password = random_password()
    admin_password = random_password()
    user_data = cloud_init(root_password, admin_password, branding_tarball())
    (SECRETS / "cloud-init.generated.yaml").write_text(user_data, encoding="utf-8")
    os.chmod(SECRETS / "cloud-init.generated.yaml", 0o600)

    created = api(
        "POST",
        "/droplets",
        {
            "name": args.name,
            "region": args.region,
            "size": args.size,
            "image": args.image,
            "ssh_keys": [ssh_id],
            "backups": False,
            "ipv6": True,
            "monitoring": True,
            "tags": ["smartvoip", "billing", "magnusbilling"],
            "user_data": user_data,
        },
    )
    droplet = created["droplet"]
    droplet_id = droplet["id"]
    print(f"Created droplet {args.name} id={droplet_id} in {args.region} size={args.size} image={args.image}")

    firewall_id = ensure_firewall(droplet_id)
    print(f"Attached cloud firewall smartvoip-billing id={firewall_id}")

    if args.wait_active:
        droplet = wait_active(droplet_id)
    ip = public_ip(droplet) or "pending"

    deployment = {
        "droplet_id": droplet_id,
        "name": args.name,
        "ip": ip,
        "region": args.region,
        "size": args.size,
        "image": args.image,
        "firewall_id": firewall_id,
        "ssh_key": str(key_path),
        "panel_url": f"http://{ip}/" if ip != "pending" else None,
        "panel_user": "root",
        "note": "Passwords are in .secrets/smartvoip-credentials.txt and /root/smartvoip-credentials.txt on the droplet. MagnusBilling compile can take 20-40 minutes.",
    }
    (SECRETS / "deployment.json").write_text(json.dumps(deployment, indent=2) + "\n", encoding="utf-8")
    creds = (
        f"panel_url=http://{ip}/\n"
        f"panel_user=root\n"
        f"panel_password={admin_password}\n"
        f"ssh_user=root\n"
        f"ssh_password={root_password}\n"
        f"ssh_key={key_path}\n"
        f"droplet_id={droplet_id}\n"
    )
    creds_path = SECRETS / "smartvoip-credentials.txt"
    creds_path.write_text(creds, encoding="utf-8")
    os.chmod(creds_path, 0o600)
    print(f"Droplet public IP: {ip}")
    print("Credentials written to .secrets/smartvoip-credentials.txt (gitignored).")
    print("First boot installs MagnusBilling and applies SmartVoIP branding; allow 20-40 minutes.")


if __name__ == "__main__":
    main()
