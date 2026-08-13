#!/usr/bin/env bash
# First-boot installer for SmartVoIP on a clean Debian droplet.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

LOG=/var/log/smartvoip-bootstrap.log
STATUS=/var/www/html/install-status.json
STAMP=/var/lib/smartvoip/installed
ROOT=/opt/smartvoip
exec > >(tee -a "${LOG}") 2>&1
on_error() {
  echo '{"status":"failed","brand":"SmartVoIP"}' > "${STATUS}"
}
trap on_error ERR

mkdir -p /var/lib/smartvoip /var/www/html "${ROOT}"
echo '{"status":"installing","brand":"SmartVoIP"}' > "${STATUS}"

if [[ -f "${STAMP}" ]]; then
  echo "SmartVoIP already installed."
  exit 0
fi

apt-get update --allow-releaseinfo-change
apt-get install -y curl wget ca-certificates python3 tar gzip

if [[ -f /root/smartvoip-branding.tar.gz ]]; then
  mkdir -p "${ROOT}"
  tar -xzf /root/smartvoip-branding.tar.gz -C "${ROOT}"
fi

INSTALLER=/root/magnusbilling-install.sh
curl -fsSL -o "${INSTALLER}" \
  https://raw.githubusercontent.com/magnussolution/magnusbilling/source/script/install.sh
chmod +x "${INSTALLER}"

python3 - <<'PY'
from pathlib import Path
p = Path("/root/magnusbilling-install.sh")
text = p.read_text(encoding="utf-8", errors="replace")
lines = []
for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("whiptail "):
        continue
    if stripped == "reboot":
        continue
    lines.append(line)
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Patched MagnusBilling installer for non-interactive SmartVoIP bootstrap.")
PY

bash "${INSTALLER}" en

if [[ -x "${ROOT}/branding/apply-branding.sh" ]]; then
  SMARTVOIP_ADMIN_PASSWORD="${SMARTVOIP_ADMIN_PASSWORD:-}" \
    bash "${ROOT}/branding/apply-branding.sh"
else
  echo "Branding overlay missing at ${ROOT}/branding/apply-branding.sh"
  echo '{"status":"failed","reason":"branding-missing"}' > "${STATUS}"
  exit 1
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STAMP}"
echo '{"status":"ready","brand":"SmartVoIP","engine":"MagnusBilling 8"}' > "${STATUS}"
echo "SmartVoIP bootstrap complete."
