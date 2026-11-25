import re
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from restaurant.business_time import current_table_window


def restaurant_date_in(days):
    return (date.fromisoformat(current_table_window()[0]) + timedelta(days=days)).isoformat()


def csrf(client):
    page = client.get("/auth/login").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)[1]


def login(client, account, password="123456"):
    return client.post("/auth/login", data={
        "account": account, "password": password, "csrf_token": csrf(client),
    })


def write(client, path, fields=None, method="POST"):
    return client.open(path, method=method, data={**(fields or {}), "csrf_token": csrf(client)})


class RestaurantTestCase(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory(prefix="usurpers-test-"))
        self.db = Path(temporary) / "restaurant.sqlite"
        self.enterContext(patch.dict("os.environ", {"USURPERS_DB_PATH": str(self.db), "USURPERS_HTTPS": "0"}))
        from app import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def signed_in(self, account, password="123456"):
        client = self.app.test_client()
        self.assertEqual(login(client, account, password).status_code, 303)
        return client
