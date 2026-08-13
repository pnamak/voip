from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ["SMARTVOICE_OCS_MOCK"] = "1"
os.environ["SMARTVOICE_ADMIN_PASSWORD"] = "testpass"
os.environ["SMARTVOICE_DATA_DIR"] = tempfile.mkdtemp(prefix="smartvoice-test-")

from fastapi.testclient import TestClient  # noqa: E402

from smartvoice.app import main as appmod  # noqa: E402
from smartvoice.app.ocs import MagnusBillingOcs, MockOcs  # noqa: E402


class OcsClientTests(unittest.TestCase):
    def test_hmac_matches_php_http_build_query(self):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["body"] = request.content.decode()
            captured["key"] = request.headers["key"]
            captured["sign"] = request.headers["sign"]
            return httpx.Response(200, json={"rows": [], "count": 0})

        import httpx

        transport = httpx.MockTransport(handler)
        client = MagnusBillingOcs("http://ocs.example/mbilling", "k" * 16, "s" * 16, transport=transport)
        client.read("user", page=1, limit=25)
        self.assertIn("/index.php/user/read", captured["url"])
        expected = hmac.new(
            b"s" * 16,
            captured["body"].encode(),
            hashlib.sha512,
        ).hexdigest()
        self.assertEqual(captured["sign"], expected)
        fields = parse_qs(captured["body"])
        self.assertEqual(fields["module"][0], "user")
        self.assertEqual(fields["action"][0], "read")
        json.loads(fields["filter"][0])

    def test_mock_create_customer_and_refill(self):
        ocs = MockOcs()
        created = ocs.create_user({"username": "carol", "firstname": "Carol", "id_group": 3, "credit": 5})
        self.assertTrue(created["success"])
        user_id = created["data"]["id"]
        refill = ocs.create("refill", {"id_user": user_id, "credit": 10, "payment": 1, "description": "test"})
        self.assertTrue(refill["success"])
        ocs.set_filter("username", "carol", "eq")
        rows = ocs.read("user")["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit"], 15)


class BssAppTests(unittest.TestCase):
    def setUp(self):
        os.environ["SMARTVOICE_OCS_MOCK"] = "1"
        os.environ["SMARTVOICE_ADMIN_PASSWORD"] = "testpass"
        os.environ["SMARTVOICE_DATA_DIR"] = tempfile.mkdtemp(prefix="smartvoice-bss-")
        appmod.reset_runtime()
        self.client = TestClient(appmod.app)

    def _login(self):
        response = self.client.post("/api/login", json={"username": "admin", "password": "testpass"})
        self.assertEqual(response.status_code, 200, response.text)

    def test_login_overlay_can_hide(self):
        css = (ROOT / "smartvoice/app/static/smartvoice.css").read_text(encoding="utf-8")
        self.assertIn(".login.hidden", css)
        self.assertIn("display: none !important", css)

    def test_customer_create_form_is_tabbed(self):
        js = (ROOT / "smartvoice/app/static/app.js").read_text(encoding="utf-8")
        css = (ROOT / "smartvoice/app/static/smartvoice.css").read_text(encoding="utf-8")
        self.assertIn("startCreate('customers')", js)
        self.assertIn("New customer", js)
        self.assertIn('data-tab="general"', js)
        self.assertIn('data-tab="personal"', js)
        self.assertIn('data-tab="supplementary"', js)
        self.assertIn(">General<", js)
        self.assertIn(">Personal<", js)
        self.assertIn(">Supplementary<", js)
        self.assertIn("startEditCustomer", js)
        self.assertIn("Bulk update", js)
        self.assertIn("applyBulkCustomers", js)
        self.assertIn("deleteCustomer(", js)
        self.assertIn(".tab-panel", css)
        self.assertIn(".tab-btn.active", css)

    def test_health_reports_bss_and_ocs(self):
        data = self.client.get("/api/health").json()
        self.assertEqual(data["role"], "bss")
        self.assertEqual(data["app"], "SmartVoice")
        self.assertEqual(data["ocs"]["mode"], "mock")

    def test_login_required(self):
        self.assertEqual(self.client.get("/api/customers").status_code, 401)

    def test_customer_payment_and_invoice_flow(self):
        self._login()
        created = self.client.post(
            "/api/customers",
            json={"username": "dina", "firstname": "Dina", "credit": 1, "typepaid": 0},
        )
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()["data"]["id"]
        self.assertEqual(created.json()["credentials"]["username"], "dina")
        self.assertTrue(created.json()["credentials"]["password"])
        customers = self.client.get("/api/customers").json()
        self.assertTrue(customers["plans"])
        self.assertTrue(any(row["username"] == "dina" for row in customers["rows"]))
        pay = self.client.post(
            "/api/payments",
            json={"ocs_user_id": user_id, "amount": 7.5, "method": "cash", "reference": "R1"},
        )
        self.assertEqual(pay.status_code, 200, pay.text)
        dashboard = self.client.get("/api/dashboard").json()
        self.assertGreaterEqual(dashboard["customers"], 1)
        invoice = self.client.post("/api/invoices", json={"ocs_user_id": 21, "period": "2026-08"})
        self.assertEqual(invoice.status_code, 200, invoice.text)
        self.assertGreaterEqual(invoice.json()["amount"], 0)

    def test_create_customer_requires_magnusbilling_user_rules(self):
        self._login()
        space = self.client.post("/api/customers", json={"username": "bad name", "firstname": "Bad", "password": "Secret9x"})
        self.assertEqual(space.status_code, 400, space.text)
        self.assertIn("space", space.json()["detail"].lower())
        short = self.client.post("/api/customers", json={"username": "ab", "firstname": "Bad", "password": "Secret9x"})
        self.assertEqual(short.status_code, 400, short.text)
        same = self.client.post(
            "/api/customers",
            json={"username": "sameuser", "firstname": "Same", "password": "sameuser"},
        )
        self.assertEqual(same.status_code, 400, same.text)
        weak = self.client.post(
            "/api/customers",
            json={"username": "weakuser", "firstname": "Weak", "password": "123456"},
        )
        self.assertEqual(weak.status_code, 400, weak.text)

    def test_create_customer_sends_full_ocs_profile(self):
        self._login()
        created = self.client.post(
            "/api/customers",
            json={
                "username": "portvila",
                "password": "PvShop#91x",
                "firstname": "Marie",
                "lastname": "Kalotiti",
                "email": "marie@portvila.example",
                "company_name": "Port Vila Shop",
                "phone": "67822100",
                "city": "Port Vila",
                "country": "VUT",
                "address": "Kumul Highway",
                "credit": 12.5,
                "typepaid": 0,
                "id_plan": 1,
                "language": "en",
                "calllimit": 2,
                "prefix_local": "678",
                "description": "Retail prepaid",
                "note": "Created from BSS",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()["data"]
        self.assertEqual(body["username"], "portvila")
        self.assertEqual(body["email"], "marie@portvila.example")
        self.assertEqual(body["company_name"], "Port Vila Shop")
        self.assertEqual(body["city"], "Port Vila")
        self.assertEqual(body["country"], "VUT")
        self.assertEqual(body["phone"], "67822100")
        self.assertEqual(body["calllimit"], 2)
        self.assertEqual(body["prefix_local"], "678")
        self.assertEqual(body["id_plan"], 1)
        self.assertEqual(body["id_group"], 3)
        customers = self.client.get("/api/customers").json()["rows"]
        row = next(item for item in customers if item["username"] == "portvila")
        self.assertEqual(row["bss_note"], "Created from BSS")
        ocs = appmod.ocs()
        ocs.clear_filter()
        ocs.set_filter("name", "portvila", "eq")
        sip_rows = ocs.read("sip")["rows"]
        ocs.clear_filter()
        self.assertTrue(sip_rows)
        self.assertEqual(sip_rows[0]["context"], "billing")
        duplicate = self.client.post(
            "/api/customers",
            json={"username": "portvila", "firstname": "Marie", "password": "OtherPass9"},
        )
        self.assertEqual(duplicate.status_code, 400, duplicate.text)

    def test_customer_edit_delete_and_bulk(self):
        self._login()
        first = self.client.post(
            "/api/customers",
            json={"username": "edita", "firstname": "Edit", "password": "EditPass91", "city": "Luganville", "credit": 8},
        )
        second = self.client.post(
            "/api/customers",
            json={"username": "editb", "firstname": "Bulk", "password": "BulkPass91", "credit": 3},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        id_a = first.json()["data"]["id"]
        id_b = second.json()["data"]["id"]
        listed = self.client.get("/api/customers").json()["rows"]
        self.assertTrue(all("password" not in row for row in listed))
        updated = self.client.put(
            f"/api/customers/{id_a}",
            json={
                "username": "edita",
                "firstname": "Marie",
                "lastname": "Kalotiti",
                "city": "Port Vila",
                "typepaid": 1,
                "id_plan": 2,
                "note": "edited from BSS",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()["data"]
        self.assertEqual(body["firstname"], "Marie")
        self.assertEqual(body["city"], "Port Vila")
        self.assertEqual(int(body["typepaid"]), 1)
        self.assertEqual(int(body["id_plan"]), 2)
        self.assertEqual(float(body["credit"]), 8)
        self.assertNotIn("password", body)
        fetched = self.client.get(f"/api/customers/{id_a}").json()["row"]
        self.assertEqual(fetched["lastname"], "Kalotiti")
        self.assertEqual(fetched["bss_note"], "edited from BSS")
        bulk = self.client.post(
            "/api/customers/bulk",
            json={"ids": [id_a, id_b], "action": "update", "active": 0, "calllimit": 4},
        )
        self.assertEqual(bulk.status_code, 200, bulk.text)
        self.assertEqual(sorted(bulk.json()["updated"]), sorted([id_a, id_b]))
        by_name = {row["username"]: row for row in self.client.get("/api/customers").json()["rows"]}
        self.assertEqual(int(by_name["edita"]["active"]), 0)
        self.assertEqual(int(by_name["editb"]["calllimit"]), 4)
        self.assertEqual(self.client.delete("/api/customers/10").status_code, 404)
        deleted = self.client.delete(f"/api/customers/{id_b}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        names = [row["username"] for row in self.client.get("/api/customers").json()["rows"]]
        self.assertNotIn("editb", names)
        self.assertIn("edita", names)
        gone = self.client.post("/api/customers/bulk", json={"ids": [id_a], "action": "delete"})
        self.assertEqual(gone.status_code, 200, gone.text)
        names = [row["username"] for row in self.client.get("/api/customers").json()["rows"]]
        self.assertNotIn("edita", names)

    def test_reseller_and_product_create(self):
        self._login()
        reseller = self.client.post(
            "/api/resellers",
            json={"username": "vanresale", "company_name": "Vanuatu Resale", "credit": 40},
        )
        self.assertEqual(reseller.status_code, 200, reseller.text)
        self.assertEqual(reseller.json()["data"]["id_group"], 2)
        product = self.client.post(
            "/api/products",
            json={"name": "Call Shop Pack", "kind": "prepaid", "monthly_fee": 15, "included_minutes": 200},
        )
        self.assertEqual(product.status_code, 200, product.text)
        catalog = self.client.get("/api/products").json()
        self.assertTrue(any(item["name"] == "Call Shop Pack" for item in catalog["catalog"]))

    def test_sip_device_monitoring(self):
        self.assertEqual(self.client.get("/api/sip-devices").status_code, 401)
        self._login()
        data = self.client.get("/api/sip-devices").json()
        self.assertGreaterEqual(data["count"], 3)
        self.assertNotIn("should-not-leak", json.dumps(data))
        by_name = {row["name"]: row for row in data["rows"]}
        self.assertEqual(by_name["alice"]["presence"], "in_call")
        self.assertEqual(by_name["bobpost"]["presence"], "offline")
        self.assertEqual(by_name["pacific-shop"]["presence"], "disabled")
        self.assertEqual(data["counts"]["in_call"], 1)
        self.assertEqual(data["counts"]["offline"], 1)
        self.assertEqual(data["counts"]["disabled"], 1)
        self.assertIn("alice", json.dumps(data))
        dashboard = self.client.get("/api/dashboard").json()
        self.assertGreaterEqual(dashboard["sip_devices"], 3)
        self.assertGreaterEqual(dashboard["sip_in_call"], 1)
        html = (ROOT / "smartvoice/app/static/index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="sip"', html)

    def test_cdr_and_failed_reports(self):
        self.assertEqual(self.client.get("/api/reports/cdr").status_code, 401)
        self.assertEqual(self.client.get("/api/reports/cdr-failed").status_code, 401)
        self._login()
        cdr = self.client.get("/api/reports/cdr").json()
        self.assertGreaterEqual(cdr["count"], 2)
        self.assertTrue(any(row["username"] == "alice" for row in cdr["rows"]))
        self.assertEqual(cdr["rows"][0]["terminate_cause"], "ANSWER")
        failed = self.client.get("/api/reports/cdr-failed").json()
        self.assertGreaterEqual(failed["count"], 3)
        self.assertTrue(any(row["terminate_cause"] == "NOANSWER" for row in failed["rows"]))
        self.assertTrue(any(row["hangup_cause"] == "User busy" for row in failed["rows"]))
        filtered = self.client.get("/api/reports/cdr-failed", params={"q": "alice"}).json()
        self.assertTrue(filtered["rows"])
        self.assertTrue(all("alice" in json.dumps(row).lower() for row in filtered["rows"]))
        csv_body = self.client.get("/api/reports/cdr.csv")
        self.assertEqual(csv_body.status_code, 200, csv_body.text)
        self.assertIn("text/csv", csv_body.headers["content-type"])
        self.assertIn("alice", csv_body.text)
        failed_csv = self.client.get("/api/reports/cdr-failed.csv")
        self.assertEqual(failed_csv.status_code, 200, failed_csv.text)
        self.assertIn("NOANSWER", failed_csv.text)
        html = (ROOT / "smartvoice/app/static/index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="cdr"', html)
        self.assertIn('data-view="cdr-failed"', html)
        self.assertIn("Reports", html)
        from smartvoice.app.reports import REPORTS

        for slug, spec in REPORTS.items():
            self.assertIn(f'data-view="{slug}"', html)
            payload = self.client.get(f"/api/reports/{slug}")
            self.assertEqual(payload.status_code, 200, f"{slug}: {payload.text}")
            body = payload.json()
            self.assertEqual(body["slug"], slug)
            self.assertEqual(body["title"], spec.title)
            self.assertIn("columns", body)
        day = self.client.get("/api/reports/summary-per-day").json()
        self.assertTrue(any(row["day"] == "2026-08-13" for row in day["rows"]))
        archive = self.client.get("/api/reports/call-archive").json()
        self.assertTrue(any(row["username"] == "alice" for row in archive["rows"]))
        did = self.client.get("/api/reports/summary-month-did").json()
        self.assertTrue(any(row["did"] == "2001" for row in did["rows"]))
        agent = self.client.get("/api/reports/summary-day-agent").json()
        self.assertTrue(any(row["username"] == "pacific" for row in agent["rows"]))
        empty_ok = self.client.get("/api/reports/summary-per-trunk")
        self.assertEqual(empty_ok.status_code, 200, empty_ok.text)

    def test_blocked_ip_security_view(self):
        self.assertEqual(self.client.get("/api/security/blocked-ip").status_code, 401)
        self._login()
        data = self.client.get("/api/security/blocked-ip").json()
        self.assertEqual(data["count"], 2)
        by_ip = {row["ip"]: row for row in data["rows"]}
        self.assertIn("203.0.113.50", by_ip)
        self.assertEqual(by_ip["203.0.113.50"]["country"], "Germany")
        self.assertIn("SIP", by_ip["203.0.113.50"]["reason"])
        self.assertEqual(by_ip["198.51.100.10"]["country"], "China")
        self.assertIn("billing panel login", by_ip["198.51.100.10"]["reason"])
        self.assertNotIn("192.0.2.8", by_ip)
        html = (ROOT / "smartvoice/app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("Security", html)
        self.assertIn('data-view="blocked-ip"', html)


class SipStatusParseTests(unittest.TestCase):
    def test_classify_and_parse_pjsip(self):
        from smartvoice.app.sip_status import (
            classify_line_status,
            extract_rtt_ms,
            parse_pjsip_contacts,
            parse_pjsip_endpoints,
        )

        self.assertEqual(classify_line_status("OK (82 ms) localhost"), "registered")
        self.assertEqual(classify_line_status("unregistered"), "offline")
        self.assertEqual(classify_line_status("Unavailable"), "unreachable")
        self.assertEqual(extract_rtt_ms("OK (82 ms) localhost"), 82)
        contacts = parse_pjsip_contacts(
            "  Contact:  test01/sip:test01@168.140.248.150:59455;rinstance=1 fac38d4987 Avail        82.703\n"
            "  Contact:  Pacnet/sip:@168.144.165.191:5060               e52748f9ad NonQual        -nan\n"
        )
        self.assertEqual(contacts["test01"]["contact"], "168.140.248.150:59455")
        self.assertEqual(contacts["test01"]["rtt_ms"], 82)
        endpoints = parse_pjsip_endpoints(
            " Endpoint:  <Endpoint/CID.....................................>  <State.....>  <Channels.>\n"
            " Endpoint:  test01                                               Not in use    0 of inf\n"
            " Endpoint:  test02/2000                                          Unavailable   0 of inf\n"
        )
        self.assertEqual(endpoints["test01"]["state"], "Not in use")
        self.assertEqual(endpoints["test02"]["state"], "Unavailable")
        self.assertEqual(endpoints["test01"]["channels"], 0)
        from smartvoice.app.sip_status import ami_command_text

        ami_text = ami_command_text(
            "Response: Success\r\nMessage: Command output follows\r\n"
            "Output: \r\n"
            "Output:   Contact:  test01/sip:test01@10.1.2.3:5060 fac Avail 12.0\r\n"
            "Output: \r\n\r\n"
        )
        parsed = parse_pjsip_contacts(ami_text)
        self.assertEqual(parsed["test01"]["contact"], "10.1.2.3:5060")


if __name__ == "__main__":
    unittest.main()
