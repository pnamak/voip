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
        customers = self.client.get("/api/customers").json()["rows"]
        self.assertTrue(any(row["username"] == "dina" for row in customers))
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


if __name__ == "__main__":
    unittest.main()
