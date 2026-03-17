import unittest

from passlib.hash import bcrypt

from app.core.security import get_password_hash, verify_password


class SecurityHashingTests(unittest.TestCase):
    def test_long_password_hashes_and_verifies_with_default_scheme(self):
        password = "A" * 120

        hashed = get_password_hash(password)

        self.assertTrue(hashed.startswith("$2"))
        self.assertTrue(verify_password(password, hashed))

    def test_legacy_bcrypt_hashes_still_verify(self):
        password = "legacy-password-123"
        hashed = bcrypt.hash(password)

        self.assertTrue(verify_password(password, hashed))


if __name__ == "__main__":
    unittest.main()
