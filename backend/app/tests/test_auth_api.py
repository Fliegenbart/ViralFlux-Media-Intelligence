import os
import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "CorrectHorseBatteryStaple123!")

from app.api import auth as auth_module
from app.api.deps import get_current_user
from app.core.rate_limit import limiter


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        limiter.reset()
        auth_module._FAILED_LOGINS.clear()
        auth_module._LOCKED_UNTIL.clear()

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(auth_module.router, prefix="/api/auth")

        @app.get("/api/protected")
        async def protected(current_user: dict = Depends(get_current_user)):
            return {"subject": current_user["sub"]}

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        limiter.reset()

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )

    def test_login_locks_after_five_failed_attempts(self) -> None:
        for _ in range(5):
            response = self._login("admin@example.com", "wrong-password")
            self.assertEqual(response.status_code, 401)

        locked = self._login("admin@example.com", "wrong-password")

        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["detail"], "Too many failed login attempts. Please try again later.")

    def test_successful_login_clears_failed_attempt_counter(self) -> None:
        for _ in range(4):
            response = self._login("admin@example.com", "wrong-password")
            self.assertEqual(response.status_code, 401)

        success = self._login("admin@example.com", "CorrectHorseBatteryStaple123!")

        self.assertEqual(success.status_code, 200)
        self.assertIn("access_token", success.json())
        self.assertFalse(auth_module._FAILED_LOGINS)
        self.assertFalse(auth_module._LOCKED_UNTIL)

    def test_login_sets_http_only_cookie_and_cookie_authenticates_requests(self) -> None:
        response = self._login("admin@example.com", "CorrectHorseBatteryStaple123!")

        self.assertEqual(response.status_code, 200)
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("samesite=lax", set_cookie.lower())

        protected = self.client.get("/api/protected")
        self.assertEqual(protected.status_code, 200)
        self.assertEqual(protected.json()["subject"], "admin@example.com")

    def test_session_endpoint_reports_authenticated_after_login(self) -> None:
        self._login("admin@example.com", "CorrectHorseBatteryStaple123!")

        session_response = self.client.get("/api/auth/session")

        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.json(),
            {
                "authenticated": True,
                "subject": "admin@example.com",
                "role": "admin",
            },
        )

    def test_logout_clears_auth_cookie_and_session(self) -> None:
        self._login("admin@example.com", "CorrectHorseBatteryStaple123!")

        logout_response = self.client.post("/api/auth/logout")
        session_response = self.client.get("/api/auth/session")

        self.assertEqual(logout_response.status_code, 200)
        self.assertIn("Max-Age=0", logout_response.headers.get("set-cookie", ""))
        self.assertEqual(session_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
