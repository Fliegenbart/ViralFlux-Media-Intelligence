import os
import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "CorrectHorseBatteryStaple123!")

from app.api import auth as auth_module
from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.database import AuditLog, Base


class AuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        self.admin_password = os.environ.get("ADMIN_PASSWORD", "CorrectHorseBatteryStaple123!")
        limiter.reset()
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine, tables=[AuditLog.__table__])
        self.db = TestingSessionLocal()

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.include_router(auth_module.router, prefix="/api/auth")

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        @app.get("/api/protected")
        async def protected(current_user: dict = Depends(get_current_user)):
            return {"subject": current_user["sub"]}

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine, tables=[AuditLog.__table__])
        self.engine.dispose()
        limiter.reset()

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )

    def test_login_locks_after_five_failed_attempts(self) -> None:
        for _ in range(5):
            response = self._login(self.admin_email, "wrong-password")
            self.assertEqual(response.status_code, 401)

        locked = self._login(self.admin_email, "wrong-password")

        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["detail"], "Too many failed login attempts. Please try again later.")

    def test_successful_login_clears_failed_attempt_counter(self) -> None:
        for _ in range(4):
            response = self._login(self.admin_email, "wrong-password")
            self.assertEqual(response.status_code, 401)

        success = self._login(self.admin_email, self.admin_password)

        self.assertEqual(success.status_code, 200)
        self.assertEqual(
            success.json(),
            {
                "authenticated": True,
                "subject": self.admin_email,
                "role": "admin",
            },
        )

    def test_login_sets_http_only_cookie_and_cookie_authenticates_requests(self) -> None:
        response = self._login(self.admin_email, self.admin_password)

        self.assertEqual(response.status_code, 200)
        set_cookie = response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("samesite=lax", set_cookie.lower())

        protected = self.client.get("/api/protected")
        self.assertEqual(protected.status_code, 200)
        self.assertEqual(protected.json()["subject"], self.admin_email)

    def test_session_endpoint_reports_authenticated_after_login(self) -> None:
        self._login(self.admin_email, self.admin_password)

        session_response = self.client.get("/api/auth/session")

        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.json(),
            {
                "authenticated": True,
                "subject": self.admin_email,
                "role": "admin",
            },
        )

    def test_session_endpoint_reports_unauthenticated_without_active_session(self) -> None:
        session_response = self.client.get("/api/auth/session")

        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.json(),
            {
                "authenticated": False,
                "subject": None,
                "role": None,
            },
        )

    def test_logout_clears_auth_cookie_and_session(self) -> None:
        login_response = self._login(self.admin_email, self.admin_password)
        set_cookie = login_response.headers.get("set-cookie", "")
        token = set_cookie.split("viralflux_session=", 1)[1].split(";", 1)[0]

        protected_before_logout = self.client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(protected_before_logout.status_code, 200)

        logout_response = self.client.post("/api/auth/logout")
        session_response = self.client.get("/api/auth/session")
        stolen_token_response = self.client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(logout_response.status_code, 200)
        self.assertIn("Max-Age=0", logout_response.headers.get("set-cookie", ""))
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.json(),
            {
                "authenticated": False,
                "subject": None,
                "role": None,
            },
        )
        self.assertEqual(stolen_token_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
