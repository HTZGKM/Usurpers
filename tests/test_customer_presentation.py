"""Rendering and asset smoke tests for the shared customer/staff entry point.

These exercise the server-rendered contracts used by guest.js without asserting
visual styling. Browser checks are still needed for layout and interactions.
"""
import json
import os
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin, urlsplit


class PageMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.data_chunks = []
        self.in_guest_data = False
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.elements.append((tag, attrs))
        if tag == "script" and attrs.get("id") == "guest-data":
            self.in_guest_data = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_guest_data = False

    def handle_data(self, data):
        if self.in_guest_data:
            self.data_chunks.append(data)

    @property
    def ids(self):
        return {attrs["id"] for _, attrs in self.elements if "id" in attrs}

    @property
    def guest_data(self):
        return json.loads("".join(self.data_chunks))

    @property
    def assets(self):
        result = set()
        for tag, attrs in self.elements:
            if tag in {"img", "script", "source"} and attrs.get("src"):
                result.add(attrs["src"])
            if tag == "link" and attrs.get("rel") in {"stylesheet", "preload", "icon"}:
                result.add(attrs.get("href", ""))
        return result


class CustomerPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="usurpers-presentation-")
        cls.addClassCleanup(cls.temp_dir.cleanup)
        cls.environment = patch.dict(os.environ, {
            "USURPERS_DB_PATH": str(Path(cls.temp_dir.name) / "presentation.db")
        })
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        # Import only after choosing an isolated database: app creates its
        # default application at import time.
        from app import create_app
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def page(self, identity=None):
        client = self.app.test_client()
        if identity:
            with client.session_transaction() as session:
                session["account"] = identity
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/html")
        return client, PageMarkup(response.get_data(as_text=True))

    def test_public_has_browsing_templates_and_login_gate(self):
        client, page = self.page()
        self.assertIsNone(page.guest_data["account"])
        self.assertEqual(page.guest_data["staffLinks"], [])
        self.assertTrue({
            "app", "nav", "close", "customer-login-prompt", "guest-data",
            "view-home", "view-menu", "view-booking", "view-account",
            "view-table", "view-delivery", "view-journal", "view-journal-archive",
            "guest-login", "guest-register", "dish-name", "bag-entry",
        }.issubset(page.ids))
        self.assertNotIn("view-workspace", page.ids)
        self.assertNotIn("reservation", page.ids)
        self.assertEqual(client.get("/auth/me").status_code, 401)
        actions = {attrs.get("data-action") for tag, attrs in page.elements if tag == "button"}
        self.assertTrue({"Home", "Menu", "Book a table", "Your table", "Journal", "My account"}.issubset(actions))

    def test_customer_has_booking_and_signed_in_controls(self):
        client, page = self.page({"customer_phone": "13900000001"})
        self.assertEqual(page.guest_data["account"]["role"], "customer")
        self.assertTrue({
            "reservation", "date", "guests", "name", "phone", "summary",
            "booking-calendar", "view-menu", "view-table",
        }.issubset(page.ids))
        self.assertNotIn("customer-login-prompt", page.ids)
        self.assertNotIn("guest-login", page.ids)
        self.assertNotIn("view-workspace", page.ids)
        self.assertEqual(client.get("/auth/me").json["user"]["role"], "customer")
        forms = [attrs for tag, attrs in page.elements if tag == "form"]
        self.assertTrue(any(attrs.get("data-account-form") == "logout" for attrs in forms))

    def test_admin_keeps_workspace_and_excludes_customer_views(self):
        client, page = self.page({"staff_id": 1})
        self.assertEqual(page.guest_data["account"]["role"], "admin")
        self.assertTrue({"view-workspace", "dp-workspace"}.issubset(page.ids))
        self.assertFalse({"view-home", "view-menu", "reservation", "dish-name"} & page.ids)
        body = next(attrs for tag, attrs in page.elements if tag == "body")
        self.assertNotIn("guest-public", body.get("class", "").split())
        self.assertIn("/static/css/admin.css", page.assets)
        self.assertIn("/static/js/admin.js", page.assets)
        self.assertEqual(client.get("/auth/me").json["user"]["role"], "admin")
        _, public = self.page()
        self.assertNotIn("/static/css/admin.css", public.assets)
        self.assertNotIn("/static/js/admin.js", public.assets)

    def test_customer_presentation_styles_do_not_leak_into_staff_roles(self):
        stylesheet = "/static/css/guest-ember.css"
        motion_script = "/static/js/guest-motion.js"
        for identity in (None, {"customer_phone": "13900000001"}):
            with self.subTest(identity=identity):
                _, page = self.page(identity)
                self.assertIn(stylesheet, page.assets)
                self.assertIn(motion_script, page.assets)
        for staff_id, role in ((1, "admin"), (2, "frontdesk"), (3, "kitchen")):
            with self.subTest(role=role):
                _, page = self.page({"staff_id": staff_id})
                self.assertEqual(page.guest_data["account"]["role"], role)
                self.assertNotIn(stylesheet, page.assets)
                self.assertNotIn(motion_script, page.assets)
                self.assertIn("/static/css/" + role + ".css", page.assets)

    def test_rendered_local_assets_and_css_dependencies_resolve(self):
        assets = set()
        for identity in (None, {"customer_phone": "13900000001"},
                         {"staff_id": 1}, {"staff_id": 2}, {"staff_id": 3}):
            _, page = self.page(identity)
            assets.update(page.assets)
        client = self.app.test_client()
        visited = set()
        while assets:
            asset = assets.pop()
            parsed = urlsplit(asset)
            if parsed.scheme or parsed.netloc or not parsed.path or parsed.path in visited:
                continue
            path = parsed.path
            visited.add(path)
            with self.subTest(asset=path), client.get(path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 0)
                if path.endswith(".css") and response.status_code == 200:
                    css = response.get_data(as_text=True)
                    for dependency in re.findall(r"url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", css):
                        if not dependency.startswith("#"):
                            assets.add(urljoin(path, dependency))
        self.assertGreater(len(visited), 10)

    def test_dynamic_dish_images_and_menu_targets_resolve(self):
        client, page = self.page()
        body = next(attrs for tag, attrs in page.elements if tag == "body")
        image_base = body["data-images"]
        actions = {attrs.get("data-action") for tag, attrs in page.elements if tag == "button"}
        for dish in page.guest_data["dishes"]:
            self.assertIn("dish:" + dish["key"], actions)
            self.assertIn("section-" + dish["category"], page.ids)
            folders = ["catalog", "detail"] if dish["category"] == "pizza" else ["catalog"]
            for folder in folders:
                path = image_base + folder + "/" + dish["key"] + ".webp"
                with self.subTest(asset=path), client.get(path) as response:
                    self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
