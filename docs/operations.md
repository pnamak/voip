# SmartVoIP operations

## Bootstrap

`smartvoip-bootstrap.service` runs once on first boot:

1. Download MagnusBilling `install.sh` from the `source` branch.
2. Strip `whiptail` and `reboot` so the install is non-interactive.
3. Run `bash install.sh en`.
4. Apply SmartVoIP branding and rotate the panel password.
5. Write `/var/www/html/install-status.json`.

Logs: `/var/log/smartvoip-bootstrap.log`.

Status: `http://DROPLET_IP/install-status.json`.

## Credentials

On the droplet, `/root/smartvoip-credentials.txt` holds the generated
panel and SSH passwords. Locally they are also in
`.secrets/smartvoip-credentials.txt`, which must stay untracked.

## SmartVoice BSS

Install or refresh the BSS on the droplet:

```bash
sudo ./deploy/smartvoice/install.sh
```

The service listens on `127.0.0.1:8088` and Apache publishes it at
`/smartvoice/`. Credentials: `/root/smartvoice-credentials.txt`.

```bash
curl -fsS http://DROPLET_IP/smartvoice/api/health
systemctl status smartvoice
```

## Health checks

```bash
curl -fsS http://DROPLET_IP/install-status.json
curl -I http://DROPLET_IP/mbilling/
curl -fsS http://DROPLET_IP/smartvoice/api/health
ssh -i .secrets/smartvoip_ed25519 root@DROPLET_IP 'asterisk -rx "core show version"'
```

## TLS

After a hostname points at the droplet:

```bash
apt-get install -y certbot python3-certbot-apache
certbot --apache -d billing.example.com
```

## Backups

MagnusBilling schedules a daily backup via `cron.php Backup`. Copy
`/usr/local/src/magnus/backup` off-box. Snapshot the droplet before
schema or trunk changes.

## Destroy

```bash
./deploy/digitalocean/destroy.sh
```

This deletes the `smartvoip-billing` droplet. It does not delete the
cloud firewall or SSH key, which can be reused.
