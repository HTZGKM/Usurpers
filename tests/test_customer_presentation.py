"""Rendering and asset smoke tests for the shared customer/staff entry point.

These exercise the server-rendered contracts used by guest.js without asserting
visual styling. Browser checks are still needed for layout and interactions.
"""
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_customer_seating_fragment_only_exposes_own_active_visit(self):
        from restaurant.db.database import get_connection

        phone = "13900001989"
        with get_connection() as db:
            db.execute(
                "INSERT INTO customers(customer_phone, name, password_hash) VALUES (?, ?, ?)",
                (phone, "Seating scope fixture", "unused"),
            )
            own = db.execute(
                """INSERT INTO dining_sessions(customer_phone, contact_name, phone_number,
                   party_size, table_id, status) VALUES (?, ?, ?, 2, 1, 'seated')""",
                (phone, "Seating scope fixture", phone),
            ).lastrowid
        try:
            public, _ = self.page()
            self.assertEqual(public.get("/?fragment=seating").status_code, 401)
            kitchen, _ = self.page({"staff_id": 3})
            self.assertEqual(kitchen.get("/?fragment=seating").status_code, 403)
            customer, _ = self.page({"customer_phone": phone})
            response = customer.get("/?fragment=seating")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            match = re.search(r'type="application/json">(.*?)</script>', response.get_data(as_text=True))
            self.assertEqual(json.loads(match.group(1)), [{"visit_id": own, "table_id": 1, "booking_id": None}])
            frontdesk, _ = self.page({"staff_id": 2})
            staff_response = frontdesk.get("/?fragment=seating")
            self.assertEqual(staff_response.status_code, 200)
            self.assertIn("Seating scope fixture", staff_response.get_data(as_text=True))
        finally:
            with get_connection() as db:
                db.execute("DELETE FROM dining_sessions WHERE visit_id = ?", (own,))
                db.execute("DELETE FROM customers WHERE customer_phone = ?", (phone,))

    def test_rendered_pages_have_browser_security_headers(self):
        client, _ = self.page()
        for path in ("/", "/auth/login"):
            with self.subTest(path=path):
                response = client.get(path)
                policy = response.headers["Content-Security-Policy"]
                self.assertIn("script-src 'self';", policy)
                self.assertIn("font-src 'self' https://fonts.gstatic.com https://cdn.fontshare.com;", policy)
                self.assertIn("form-action 'self';", policy)
                self.assertIn("frame-ancestors 'none'", policy)
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_missing_page_uses_html_and_missing_api_uses_json(self):
        client = self.app.test_client()
        path = "/missing-restaurant-page"
        page = client.get(path, headers={"Accept": "text/html,application/json;q=0.5"})
        self.assertEqual((page.status_code, page.mimetype), (404, "text/html"))
        self.assertIn(b"Page not found", page.data)
        self.assertIn(b' href="/"', page.data)
        self.assertIn("Accept", page.vary)
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])

        api = client.get(path, headers={"Accept": "application/json"})
        self.assertEqual((api.status_code, api.mimetype), (404, "application/json"))
        self.assertEqual(api.json["error"], "NOT_FOUND")
        self.assertIn("Accept", api.vary)
        self.assertEqual(client.get(path, headers={"Accept": "*/*"}).mimetype, "text/html")

    def test_method_error_preserves_allow_header(self):
        client = self.app.test_client()
        for accept in ("text/html", "application/json"):
            with self.subTest(accept=accept):
                response = client.post("/menu", headers={"Accept": accept})
                self.assertEqual((response.status_code, response.mimetype), (405, accept))
                self.assertIn("GET", response.allow)

    def test_internal_errors_keep_page_and_api_responses_separate(self):
        guest = self.app.test_client()
        kitchen, _ = self.page({"staff_id": 3})
        internal_message = "isolated fixture error details"
        with patch("app.restaurant_view", side_effect=RuntimeError(internal_message)):
            with self.assertLogs(self.app.logger.name, level="ERROR"):
                failed_page = guest.get("/", headers={"Accept": "text/html"})
        self.assertEqual((failed_page.status_code, failed_page.mimetype), (500, "text/html"))
        self.assertIn(b"Something went wrong", failed_page.data)
        self.assertNotIn(internal_message.encode(), failed_page.data)

        with patch("restaurant.services.kitchen_service.get_waiting_items", side_effect=RuntimeError(internal_message)):
            with self.assertLogs(self.app.logger.name, level="ERROR"):
                failed_api = kitchen.get("/kitchen/queue", headers={"Accept": "text/html"})
        self.assertEqual((failed_api.status_code, failed_api.mimetype), (500, "application/json"))
        self.assertEqual(failed_api.json["error"], "INTERNAL_SERVER_ERROR")
        self.assertNotIn(internal_message.encode(), failed_api.data)

    def test_menu_escapes_description_in_markup_and_json(self):
        from restaurant.db.database import get_connection

        description = '<span data-security-fixture="plain">Warm & mild</span>'
        with get_connection() as db:
            previous = db.execute("SELECT ingredients FROM dishes WHERE dish_id=1").fetchone()[0]
            db.execute("UPDATE dishes SET ingredients=? WHERE dish_id=1", (description,))
        try:
            client, page = self.page()
            html = client.get("/").get_data(as_text=True)
            self.assertNotIn(description, html)
            self.assertIn("&lt;span", html)
            self.assertEqual(next(dish for dish in page.guest_data["dishes"] if dish["id"] == 1)["description"],
                             description)
        finally:
            with get_connection() as db:
                db.execute("UPDATE dishes SET ingredients=? WHERE dish_id=1", (previous,))

    def test_live_forms_validate_csrf_and_role_before_mutation(self):
        from restaurant.db.database import get_connection

        day = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
        fields = {"booking_date": day, "time_slot_id": "2", "party_size": "1"}
        customer, page = self.page({"customer_phone": "13900000001"})
        frontdesk, desk_page = self.page({"staff_id": 2})
        kitchen, _ = self.page({"staff_id": 3})
        admin, _ = self.page({"staff_id": 1})

        def token(markup):
            return next(attrs["content"] for tag, attrs in markup.elements
                        if tag == "meta" and attrs.get("name") == "restaurant-csrf")

        with get_connection() as db:
            counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("bookings", "dishes", "dining_sessions", "kitchen_queue")}
        examples = (
            (customer, "/bookings", fields),
            (frontdesk, "/frontdesk/visits/1/close", {}),
            (kitchen, "/kitchen/items/9001/start", {}),
            (admin, "/admin/dishes/1/archive", {}),
        )
        for client, path, form in examples:
            for provided in ({}, {"csrf_token": "invalid-fixture"}):
                with self.subTest(path=path, token_present=bool(provided)):
                    response = client.post(path, data={**form, **provided})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("csrf_token", response.json["errors"])
        self.assertEqual(customer.post("/bookings", data={**fields, "csrf_token": token(desk_page)}).status_code, 400)
        self.assertEqual(customer.post("/admin/dishes/1/archive", data={"csrf_token": token(page)}).status_code, 403)
        logout_without_token = customer.post("/auth/logout")
        self.assertEqual(logout_without_token.status_code, 400)
        self.assertEqual(customer.get("/auth/me").status_code, 200)
        with get_connection() as db:
            for table, count in counts.items():
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count)
            self.assertEqual(db.execute("SELECT is_archived FROM dishes WHERE dish_id=1").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT status FROM dining_sessions WHERE visit_id=1").fetchone()[0], "seated")
            self.assertEqual(db.execute("SELECT status FROM kitchen_queue WHERE order_item_id=9001").fetchone()[0], "waiting")
        response = customer.post("/bookings", data={**fields, "csrf_token": token(page)})
        self.assertEqual(response.status_code, 201)
        booking_id = response.json["booking"]["booking_id"]
        with get_connection() as db:
            db.execute("DELETE FROM bookings WHERE booking_id=?", (booking_id,))

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
