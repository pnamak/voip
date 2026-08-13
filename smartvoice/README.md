# SmartVoice BSS

SmartVoice is the **Business Support System** for this platform. It is a
separate application from MagnusBilling.

MagnusBilling 8 is the **Online Charging System (OCS)**. It tracks and charges
calls as they happen, keeps prepaid wallets from going negative, and rates
postpaid usage to the second.

SmartVoice uses the MagnusBilling API as that charging engine. Operators manage
customers, products, payments, invoices, and resellers in SmartVoice. Live
balances, SIP accounts, and CDRs stay in MagnusBilling.

```text
Operator browser
    -> SmartVoice BSS  (/smartvoice/)
           |  HMAC API (customers, plans, refills, CDRs)
           v
    MagnusBilling OCS  (/mbilling/)
           -> MariaDB + Asterisk 20 / PJSIP
```

## Run locally (mock OCS)

```bash
export SMARTVOICE_OCS_MOCK=1
export SMARTVOICE_ADMIN_PASSWORD=smartvoice
./smartvoice/scripts/run.sh
```

Open http://127.0.0.1:8088/ and sign in as `admin` / `smartvoice`.

## Run against a live MagnusBilling OCS

```bash
export SMARTVOICE_OCS_URL=http://127.0.0.1/mbilling
export SMARTVOICE_OCS_KEY=your_api_key
export SMARTVOICE_OCS_SECRET=your_api_secret
export SMARTVOICE_OCS_MOCK=0
./smartvoice/scripts/run.sh
```

Create the API key in MagnusBilling (Users → API) with `crud` permission, or
run `deploy/smartvoice/install.sh` on the droplet.

## Tests

```bash
python3 smartvoice/tests/test_app.py
```
