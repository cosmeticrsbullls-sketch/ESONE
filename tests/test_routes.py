import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
from fastapi.testclient import TestClient
from main import app


class PublicRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_home_and_login_without_database(self):
        for path in ("/", "/login", "/login/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('action="/login"', response.text)

    def test_literal_wildcard_recovers_home(self):
        for path in ("/**", "/%2A%2A"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/")
        self.assertEqual(self.client.get("/**").status_code, 200)

    def test_unknown_route_is_still_not_found(self):
        self.assertEqual(self.client.get("/does-not-exist").status_code, 404)

    def test_health_without_database(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "service": "ESONE"})

    def test_protected_routes_redirect(self):
        for path in ("/command-center", "/clients", "/users", "/mobile", "/visits"):
            self.assertEqual(self.client.get(path, follow_redirects=False).status_code, 303)
