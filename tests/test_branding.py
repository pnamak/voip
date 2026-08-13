#!/usr/bin/env python3
import hashlib
import re
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_brand_files_exist(self):
        required = [
            ROOT / "branding/brand.conf",
            ROOT / "branding/assets/logo.svg",
            ROOT / "branding/web/branding.js",
            ROOT / "branding/web/landing.html",
            ROOT / "branding/web/smartvoip.css",
            ROOT / "branding/sql/branding.sql",
            ROOT / "branding/apply-branding.sh",
            ROOT / "deploy/digitalocean/deploy.py",
            ROOT / "deploy/digitalocean/bootstrap.sh",
        ]
        missing = [str(path) for path in required if not path.exists()]
        self.assertEqual(missing, [])

    def test_branding_js_sets_product_name(self):
        text = (ROOT / "branding/web/branding.js").read_text(encoding="utf-8")
        self.assertIn("SmartVoIP", text)
        self.assertIn("nameCustom", text)
        self.assertIn("logoCustom", text)

    def test_landing_page_links_to_panel(self):
        text = (ROOT / "branding/web/landing.html").read_text(encoding="utf-8")
        self.assertIn("/mbilling/", text)
        self.assertIn("SmartVoIP", text)

    def test_sql_updates_login_header(self):
        text = (ROOT / "branding/sql/branding.sql").read_text(encoding="utf-8")
        self.assertIn("login_header", text)
        self.assertIn("Sign in to SmartVoIP", text)

    def test_default_magnus_password_hash(self):
        self.assertEqual(
            hashlib.sha1(b"magnus").hexdigest(),
            "9f4ca770b638615ac5c3e0d2da16b77c80c2f2c6",
        )

    def test_gitignore_keeps_secrets_out_of_git(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".secrets/", text)
        self.assertIn(".env", text)

    def test_tracked_files_do_not_contain_do_tokens(self):
        pattern = re.compile(r"dop_v1_[a-f0-9]{64}")
        tracked = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", ".secrets", "__pycache__"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if pattern.search(text):
                tracked.append(str(path.relative_to(ROOT)))
        self.assertEqual(tracked, [])

    def test_cloud_init_is_ascii_yaml(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "deploy", ROOT / "deploy/digitalocean/deploy.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = module.cloud_init(
            "Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8",
            "Aa1Bb2Cc3Dd4Ee5Ff6Gg7Hh8",
            module.branding_tarball(),
        )
        text.encode("ascii")
        self.assertTrue(text.startswith("#cloud-config"))
        self.assertIn("encoding: b64", text)
        self.assertIn("smartvoip-bootstrap.service", text)
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "deploy", ROOT / "deploy/digitalocean/deploy.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        blob = module.branding_tarball()
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as handle:
            handle.write(blob)
            handle.flush()
            with tarfile.open(handle.name, "r:gz") as tar:
                names = tar.getnames()
        self.assertTrue(any(name.endswith("branding/apply-branding.sh") for name in names))
        self.assertTrue(any(name.endswith("branding/web/branding.js") for name in names))


if __name__ == "__main__":
    unittest.main()
