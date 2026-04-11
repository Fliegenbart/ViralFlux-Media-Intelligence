import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "CorrectHorseBatteryStaple123!")

from app.api import auth as auth_module


class AuthUserRegistryTests(unittest.TestCase):
    def test_build_auth_users_supports_static_registry_entries(self) -> None:
        settings = SimpleNamespace(
            AUTH_USER_REGISTRY_JSON="""
            [
              {"email": "admin@example.com", "password": "CorrectHorseBatteryStaple123!", "role": "admin"},
              {"username": "viewer@example.com", "password": "AnotherStrongPassword123!", "role": "viewer"}
            ]
            """,
            ADMIN_EMAIL=None,
            ADMIN_PASSWORD=None,
        )

        users = auth_module._build_auth_users(settings)

        self.assertEqual(sorted(users.keys()), ["admin@example.com", "viewer@example.com"])
        self.assertEqual(users["admin@example.com"]["role"], "admin")
        self.assertEqual(users["viewer@example.com"]["role"], "viewer")
        self.assertEqual(users["viewer@example.com"]["subject"], "viewer@example.com")
        self.assertTrue(
            auth_module.verify_password(
                "AnotherStrongPassword123!",
                users["viewer@example.com"]["password"],
            )
        )

    def test_build_auth_users_rejects_unknown_roles(self) -> None:
        settings = SimpleNamespace(
            AUTH_USER_REGISTRY_JSON="""
            [{"email": "ops@example.com", "password": "CorrectHorseBatteryStaple123!", "role": "superboss"}]
            """,
            ADMIN_EMAIL=None,
            ADMIN_PASSWORD=None,
        )

        with self.assertRaises(RuntimeError):
            auth_module._build_auth_users(settings)

    def test_build_auth_users_falls_back_to_legacy_admin_credentials(self) -> None:
        settings = SimpleNamespace(
            AUTH_USER_REGISTRY_JSON=None,
            ADMIN_EMAIL="Admin@Example.com",
            ADMIN_PASSWORD="CorrectHorseBatteryStaple123!",
        )

        users = auth_module._build_auth_users(settings)

        self.assertEqual(list(users.keys()), ["admin@example.com"])
        self.assertEqual(users["admin@example.com"]["role"], "admin")
        self.assertEqual(users["admin@example.com"]["subject"], "admin@example.com")


if __name__ == "__main__":
    unittest.main()
