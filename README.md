# SmartVoIP Billing Platform

SmartVoIP is a branded [MagnusBilling 8](https://github.com/magnussolution/magnusbilling)
billing, routing, and management platform for VoIP providers, call shops, and
telephony services.

The MagnusBilling engine stays upstream. This repository adds SmartVoIP
branding, a landing page, and DigitalOcean automation that provisions a
Debian droplet, installs MagnusBilling non-interactively, and applies the
brand overlay.

## What you get

- prepaid and postpaid customer billing
- rates, trunks, providers, and call routing
- SIP/PJSIP accounts, DIDs, IVRs, queues, callbacks, and calling cards
- CDRs, invoices, refills, vouchers, and reseller administration
- call-shop workflows
- a SmartVoIP login panel, logo, and landing page on top of MagnusBilling 8
- Asterisk 20 / PJSIP, Apache, PHP, MariaDB, Fail2ban, and host firewall

## Architecture

```text
Browser
  -> SmartVoIP landing page
  -> MagnusBilling web panel (Ext JS + Yii)
  -> MariaDB
  -> Asterisk 20 / PJSIP  -> carriers and SIP devices
```

## DigitalOcean deploy

MagnusBilling must run on a **clean dedicated server**. The installer
compiles Asterisk and reboots-capable services; first boot commonly takes
20–40 minutes.

1. Create a DigitalOcean personal access token with Droplet and Firewall
   write scope. Do not commit it.
2. Export it in your shell:

   ```bash
   export DIGITALOCEAN_TOKEN=dop_v1_your_token
   ```

3. Deploy:

   ```bash
   ./deploy/digitalocean/deploy.sh
   ```

Defaults (overridable with `DO_REGION`, `DO_SIZE`, `DO_IMAGE`,
`DO_DROPLET_NAME`):

| Setting | Default | Reason |
| --- | --- | --- |
| Region | `syd1` | Matches existing Pacnet Sydney droplets |
| Size | `s-2vcpu-4gb-amd` | MagnusBilling recommends 4 GB RAM |
| Image | `debian-13-x64` | Supported by MagnusBilling 8 |
| Name | `smartvoip-billing` | Stable name used by destroy |

The script creates an SSH key, a cloud firewall (SSH, HTTP/S, SIP, RTP),
and a droplet. Credentials are written to gitignored
`.secrets/smartvoip-credentials.txt` and to `/root/smartvoip-credentials.txt`
on the server.

Destroy:

```bash
./deploy/digitalocean/destroy.sh
```

### First login

1. Open `http://DROPLET_IP/`
2. Wait until the status chip says **Platform ready**
3. Open the billing panel at `/mbilling/`
4. Sign in as `root` with the generated password
5. Change that password immediately

Default MagnusBilling `root` / `magnus` is replaced during branding.

## Branding overlay

`branding/apply-branding.sh` can also be run on an already-installed
MagnusBilling server:

```bash
export MBILLING_ROOT=/var/www/html/mbilling
sudo -E ./branding/apply-branding.sh
```

It sets the product name, landing page, logo, login header, theme, and
administrator company fields. Runtime hooks (`window.nameCustom`,
`window.productCustom`, `window.logoCustom`) are the supported MagnusBilling
white-label entry points.

## Security

- Never commit DigitalOcean tokens, SSH private keys, or panel passwords.
- Rotate any token that was pasted into chat, tickets, or a repository.
- Restrict SSH and the web panel to trusted networks when you have a
  stable operator IP.
- Add TLS with a domain and Let's Encrypt after DNS points at the droplet.
- SIP (`5060`) and RTP (`10000-20000/udp`) are required for live calls.

## License

MagnusBilling and this overlay are LGPL-3.0. See `LICENSE`.
