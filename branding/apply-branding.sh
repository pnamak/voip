#!/usr/bin/env bash
# Apply SmartVoIP branding to an installed MagnusBilling tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=brand.conf
source "${ROOT_DIR}/branding/brand.conf"

export MBILLING_ROOT="${MBILLING_ROOT:-/var/www/html/mbilling}"
export WEB_ROOT="${WEB_ROOT:-/var/www/html}"
export STATUS_FILE="${STATUS_FILE:-${WEB_ROOT}/install-status.json}"
export SMARTVOIP_ADMIN_PASSWORD="${SMARTVOIP_ADMIN_PASSWORD:-}"

if [[ ! -f "${MBILLING_ROOT}/index.html" ]]; then
  echo "MagnusBilling is not installed at ${MBILLING_ROOT}" >&2
  exit 1
fi

install -d -m 0755 "${WEB_ROOT}/branding"
install -m 0644 "${ROOT_DIR}/branding/assets/logo.svg" "${WEB_ROOT}/branding/logo.svg"
install -m 0644 "${ROOT_DIR}/branding/web/smartvoip.css" "${WEB_ROOT}/branding/smartvoip.css"
install -m 0644 "${ROOT_DIR}/branding/web/landing.html" "${WEB_ROOT}/index.html"
install -m 0644 "${ROOT_DIR}/branding/assets/logo.svg" "${MBILLING_ROOT}/resources/images/smartvoip-logo.svg"
install -m 0644 "${ROOT_DIR}/branding/web/branding.js" "${MBILLING_ROOT}/branding.js"

python3 - <<'PY'
from pathlib import Path
import os
import re

root = Path(os.environ.get("MBILLING_ROOT", "/var/www/html/mbilling"))
index = root / "index.html"
text = index.read_text(encoding="utf-8", errors="replace")
if "branding.js" not in text:
    text = text.replace(
        '<script src="locale.js">',
        '<script src="branding.js"></script>\n    <script src="locale.js">',
        1,
    )
text = re.sub(r"<title>\s*MagnusBilling\s*</title>", "<title>SmartVoIP</title>", text, count=1)
text = text.replace(
    "document.getElementById('name-system').innerHTML = t('MagnusBilling System');",
    "document.getElementById('name-system').innerHTML = window.agentTitle || 'SmartVoIP';",
)
text = text.replace(
    "document.getElementById('text-msg').innerHTML = 'Voip System';",
    "document.getElementById('text-msg').innerHTML = 'SmartVoIP Billing Platform';",
)
index.write_text(text, encoding="utf-8")

about = root / "classic/src/view/main/About.js"
if about.exists():
    about_text = about.read_text(encoding="utf-8", errors="replace")
    about_text = about_text.replace("resources/images/logo.png", "resources/images/smartvoip-logo.svg")
    about_text = about_text.replace(
        "MagnusBilling is a FREE system to VoIP providers",
        "SmartVoIP is a branded MagnusBilling platform for VoIP providers, call shops, and telephony services",
    )
    about_text = about_text.replace(
        'href="http://www.magnusbilling.org">www.magnusbilling.org',
        'href="https://github.com/magnussolution/magnusbilling">magnusbilling',
    )
    about.write_text(about_text, encoding="utf-8")

main = root / "protected/config/main.php"
if main.exists():
    main.write_text(
        main.read_text(encoding="utf-8", errors="replace").replace(
            "'name'       => 'MagnusBilling'",
            "'name'       => 'SmartVoIP'",
        ),
        encoding="utf-8",
    )
print("Patched MagnusBilling UI files for SmartVoIP branding.")
PY

if command -v mariadb >/dev/null 2>&1; then
  mariadb --protocol=socket mbilling < "${ROOT_DIR}/branding/sql/branding.sql" || true
fi

if [[ -n "${SMARTVOIP_ADMIN_PASSWORD:-}" ]]; then
  HASH="$(python3 - <<PY
import hashlib, os
print(hashlib.sha1(os.environ["SMARTVOIP_ADMIN_PASSWORD"].encode()).hexdigest())
PY
)"
  mariadb --protocol=socket mbilling -e "UPDATE pkg_user SET password='${HASH}' WHERE username='root';"
  echo "Updated SmartVoIP administrator password."
fi

PUBLIC_IP="$(curl -4 -fsS https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
if command -v mariadb >/dev/null 2>&1; then
  mariadb --protocol=socket mbilling -e "UPDATE pkg_configuration SET config_value='${PUBLIC_IP}' WHERE config_key='ip_servers';" || true
fi

cat > "${STATUS_FILE}" <<EOF
{"status":"ready","brand":"${BRAND_NAME}","engine":"${BRAND_ENGINE}"}
EOF

echo "SmartVoIP branding applied."
