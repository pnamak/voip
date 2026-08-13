#!/usr/bin/env bash
# Install SmartVoice BSS on the MagnusBilling / SmartVoIP droplet.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/smartvoice}"
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OCS_URL="${SMARTVOICE_OCS_URL:-http://127.0.0.1/mbilling}"
ADMIN_PASSWORD="${SMARTVOICE_ADMIN_PASSWORD:-}"
API_KEY="${SMARTVOICE_OCS_KEY:-}"
API_SECRET="${SMARTVOICE_OCS_SECRET:-}"

if [[ -z "${ADMIN_PASSWORD}" ]]; then
  ADMIN_PASSWORD="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(20)))
PY
)"
fi
if [[ -z "${API_KEY}" ]]; then
  API_KEY="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(24)))
PY
)"
fi
if [[ -z "${API_SECRET}" ]]; then
  API_SECRET="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(24)))
PY
)"
fi

install -d -m 0755 "${APP_ROOT}"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y python3-venv python3-pip
rm -rf "${APP_ROOT}/smartvoice"
cp -a "${SRC_ROOT}/smartvoice" "${APP_ROOT}/smartvoice"
python3 -m venv "${APP_ROOT}/venv"
"${APP_ROOT}/venv/bin/pip" install --upgrade pip
"${APP_ROOT}/venv/bin/pip" install -r "${APP_ROOT}/smartvoice/requirements.txt"

install -d -m 0750 "${APP_ROOT}/data"
cat > "${APP_ROOT}/env" <<EOF
SMARTVOICE_HOST=127.0.0.1
SMARTVOICE_PORT=8088
SMARTVOICE_DATA_DIR=${APP_ROOT}/data
SMARTVOICE_SECRET=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)
SMARTVOICE_ADMIN_USER=admin
SMARTVOICE_ADMIN_PASSWORD=${ADMIN_PASSWORD}
SMARTVOICE_OCS_URL=${OCS_URL}
SMARTVOICE_OCS_KEY=${API_KEY}
SMARTVOICE_OCS_SECRET=${API_SECRET}
SMARTVOICE_OCS_MOCK=0
EOF
chmod 600 "${APP_ROOT}/env"

if command -v mariadb >/dev/null 2>&1; then
  mariadb --protocol=socket mbilling <<SQL
INSERT INTO pkg_api (id_user, status, api_key, api_secret, api_restriction_ips, action)
SELECT 1, 1, '${API_KEY}', '${API_SECRET}', '127.0.0.1,::1', 'crud'
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM pkg_api WHERE api_key = '${API_KEY}');
SQL
  PLAN_COUNT="$(mariadb --protocol=socket mbilling -N -e 'SELECT COUNT(*) FROM pkg_plan')"
  if [[ "${PLAN_COUNT}" == "0" ]]; then
    mariadb --protocol=socket mbilling -e "INSERT INTO pkg_plan (id_user, name, ini_credit, signup, lcrtype) VALUES (1, 'SmartVoice Default', 5, 1, 0);"
  fi
fi

cat > /etc/systemd/system/smartvoice.service <<EOF
[Unit]
Description=SmartVoice BSS
After=network.target apache2.service mariadb.service
Wants=network.target

[Service]
Type=simple
EnvironmentFile=${APP_ROOT}/env
WorkingDirectory=${APP_ROOT}
ExecStart=${APP_ROOT}/venv/bin/uvicorn smartvoice.app.main:app --host 127.0.0.1 --port 8088 --app-dir ${APP_ROOT}
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/apache2/conf-available/smartvoice.conf <<'EOF'
RedirectMatch ^/smartvoice$ /smartvoice/
ProxyPreserveHost On
ProxyPass /smartvoice/ http://127.0.0.1:8088/
ProxyPassReverse /smartvoice/ http://127.0.0.1:8088/
<Location /smartvoice/>
    Require all granted
</Location>
EOF

a2enmod proxy proxy_http >/dev/null
a2enconf smartvoice >/dev/null
systemctl daemon-reload
systemctl enable --now smartvoice.service
systemctl reload apache2

umask 077
cat > /root/smartvoice-credentials.txt <<EOF
SmartVoice BSS
URL: http://SERVER_IP/smartvoice/
Username: admin
Password: ${ADMIN_PASSWORD}
OCS engine: MagnusBilling at ${OCS_URL}
EOF
chmod 600 /root/smartvoice-credentials.txt
echo "SmartVoice BSS installed. Open /smartvoice/"
