import sqlite3
import unittest

from backend import app


class AccountTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(app.SCHEMA.read_text(encoding="utf-8"))
        self.addCleanup(self.db.close)
        self.at = "2026-11-12T10:00:00+07:00"

    def call(self, path, token="", method="POST", **data):
        with self.db:
            return app.dispatch(self.db, method, path, {}, data, "Bearer " + token, self.at)

    def signup(self, username, role="owner", **extra):
        return self.call("/signup", username=username, name=username, role=role,
                         password="First-password-123", confirm_password="First-password-123",
                         birth_date="2000-01-15", gender="other", email=username+"@example.com",
                         phone="090" + str(sum(ord(char) for char in username)).zfill(7), **extra)

    def login(self, username, password="First-password-123", **extra):
        return self.call("/login", username=username, password=password, **extra)

    def test_registration_details_and_validation(self):
        data = dict(username="new-user", birth_date="2001-05-17", gender="female",
                    email="New@Example.com", phone="090 123 4567", role="employee", shop_id=1,
                    password="Valid-password-123", confirm_password="Valid-password-123")
        for key, invalid in (("birth_date", "2030-01-01"), ("birth_date", "2001-02-30"),
                             ("gender", ""), ("email", "invalid"), ("phone", "abc"),
                             ("confirm_password", "different")):
            with self.subTest(key=key, invalid=invalid):
                with self.assertRaises(app.APIError):
                    self.call("/signup", **dict(data, **{key: invalid}))
                self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
        self.call("/signup", **data)
        details = self.db.execute("SELECT * FROM account_details").fetchone()
        self.assertEqual(details["birth_date"], data["birth_date"])
        self.assertEqual(details["gender"], "female")
        self.assertEqual(details["email"], "new@example.com")
        self.assertEqual(details["phone"], "+84901234567")
        with self.assertRaises(app.APIError) as error:
            self.call("/signup", **dict(data, username="other-user"))
        self.assertEqual(error.exception.status, 409)

    def test_roles_approval_recovery_and_session_revocation(self):
        owner = self.signup("owner")
        self.assertEqual(owner["status"], "active")
        token = self.login("owner")["token"]
        staff = self.signup("staff", role="employee", shop_id=1)
        manager = self.signup("manager")
        for username in ("staff", "manager"):
            with self.assertRaises(app.APIError) as error:
                self.login(username)
            self.assertEqual(error.exception.status, 403)
        waiting = self.call("/account-registrations", token, method="GET")
        self.assertEqual(len(waiting), 2)
        for account in waiting:
            self.call(f"/account-registrations/{account['id']}/approve", token, hourly_rate=25000)
        employee_token = self.login("staff")["token"]
        self.assertEqual(self.call("/me", employee_token, method="GET")["shop_id"], 1)
        self.assertEqual(self.login("manager")["role"], "owner")
        with self.assertRaises(app.APIError):
            self.call("/change-password", employee_token, current_password="wrong",
                      new_password="Second-password-123")
        self.call("/change-password", employee_token, current_password="First-password-123",
                  new_password="Second-password-123")
        with self.assertRaises(app.APIError):
            self.call("/me", employee_token, method="GET")
        updated_token = self.login("staff", password="Second-password-123")["token"]
        with self.assertRaises(app.APIError):
            self.call("/reset-password", username="staff", recovery_code="incorrect",
                      new_password="Third-password-123")
        reset = self.call("/reset-password", username="staff", recovery_code=staff["recovery_code"],
                          new_password="Third-password-123")
        self.assertNotEqual(reset["recovery_code"], staff["recovery_code"])
        with self.assertRaises(app.APIError):
            self.call("/me", updated_token, method="GET")
        with self.assertRaises(app.APIError):
            self.call("/reset-password", username="staff", recovery_code=staff["recovery_code"],
                      new_password="Fourth-password-123")
        self.login("staff", password="Third-password-123")

    def test_remember_expiry_logout_and_legacy_recovery(self):
        self.signup("owner")
        normal = self.login("owner")
        remembered = self.login("owner", remember=True)
        self.assertEqual(normal["expires"], "2026-11-12T22:00:00+07:00")
        self.assertEqual(remembered["expires"], "2026-12-12T10:00:00+07:00")
        self.at = "2026-11-13T10:00:00+07:00"
        with self.assertRaises(app.APIError):
            self.call("/me", normal["token"], method="GET")
        self.call("/me", remembered["token"], method="GET")
        self.call("/logout", remembered["token"])
        with self.assertRaises(app.APIError):
            self.call("/me", remembered["token"], method="GET")
        encoded = app.encode_password("Legacy-password-123")
        self.db.execute("INSERT INTO users(username,name,password) VALUES ('legacy','Legacy',?)", (encoded,))
        token = self.login("legacy", password="Legacy-password-123")["token"]
        result = self.call("/recovery-code", token, current_password="Legacy-password-123")
        self.call("/reset-password", username="legacy", recovery_code=result["recovery_code"],
                  new_password="Updated-password-123")
        self.login("legacy", password="Updated-password-123")


if __name__ == "__main__":
    unittest.main()
