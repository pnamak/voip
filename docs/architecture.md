# SmartVoIP architecture

SmartVoIP is an operator-facing brand on top of MagnusBilling 8. It does not
replace the billing engine. The DigitalOcean droplet is a dedicated
telephony host, not a containerized app platform.

## Components

| Layer | Role |
| --- | --- |
| Landing page | `/var/www/html/index.html` SmartVoIP status and entry |
| Web panel | `/var/www/html/mbilling` MagnusBilling Ext JS + Yii |
| Database | MariaDB schema `mbilling`, local Unix socket root, app user `mbillingUser` |
| Switch | Asterisk 20 with PJSIP, AGI at `resources/asterisk/mbilling.php` |
| Jobs | `cron.php` plus MagnusBilling crontab entries |
| Host security | firewalld, Fail2ban, DigitalOcean cloud firewall |

## Branding path

1. Official installer downloads MagnusBilling 8 and compiles Asterisk.
2. `branding/apply-branding.sh` copies logo, `branding.js`, landing page, and SQL defaults.
3. `branding.js` sets `window.nameCustom`, `window.productCustom`, and `window.logoCustom`.
4. `pkg_configuration.login_header` and `pkg_user.company_name` complete panel copy.

## Ports

| Port | Use |
| --- | --- |
| 22/tcp | SSH |
| 80/tcp, 443/tcp | Landing page and billing panel |
| 5060/udp+tcp, 5061/tcp | SIP / SIP TLS |
| 10000-20000/udp | RTP media |

AMI stays on localhost. Do not publish MariaDB.
