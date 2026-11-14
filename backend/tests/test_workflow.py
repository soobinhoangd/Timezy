import io
import sqlite3
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from openpyxl import load_workbook

from backend import app as backend


class WorkflowTest(unittest.TestCase):
    def test_checkin_checkout_time_boundaries(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.executescript(backend.SCHEMA.read_text(encoding="utf-8"))
        db.execute("INSERT INTO users VALUES (1,'staff','Staff','unused',1,25000)")
        db.execute("UPDATE account_profiles SET status='active'")
        db.execute("INSERT INTO sessions VALUES (?,1,'2026-11-20T00:00:00+07:00')",
                   (backend.hashlib.sha256(b"test-token").hexdigest(),))
        db.execute("""INSERT INTO shifts VALUES
                      (1,1,'2026-11-15T22:00:00+07:00','2026-11-16T02:00:00+07:00',1)""")
        db.execute("INSERT INTO attendance(shift_id,user_id,hourly_rate) VALUES (1,1,25000)")
        db.commit()

        def call(action, at):
            with db:
                return backend.dispatch(db, "POST", "/attendance/1/"+action, {}, {},
                                        "Bearer test-token", at+"+07:00")

        with self.assertRaises(backend.APIError):
            call("check-in", "2026-11-15T21:59:59")
        self.assertIsNotNone(call("check-in", "2026-11-15T22:00:00")["check_in"])
        with self.assertRaises(backend.APIError):
            call("check-out", "2026-11-16T02:00:01")
        self.assertEqual(call("check-out", "2026-11-16T02:00:00")["pay"], 100000)

    def test_database_initialization_preserves_accounts(self):
        from database.connection import connect, initialize

        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            path = Path(directory) / "data" / "test.sqlite3"
            initialize(path)
            db = connect(path)
            try:
                db.execute("INSERT INTO users(username,name,password,shop_id) VALUES ('existing','Existing','hash',1)")
                db.execute("INSERT INTO weekly_availability VALUES (1,'2026-11-16','morning')")
                db.execute("PRAGMA user_version=5")
                db.commit()
            finally:
                db.close()
            initialize(path)
            db = connect(path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT status FROM account_profiles").fetchone()[0], "pending")
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 9)
                self.assertEqual(db.execute("SELECT week_start FROM weekly_submissions").fetchone()[0], "2026-11-16")
            finally:
                db.close()

    def test_shift_to_excel(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(backend.SCHEMA.read_text(encoding="utf-8"))
        at = "2026-10-10T11:00:00+07:00"
        salt = "12" * 16
        password = "test-password"
        encoded = f"{salt}:{backend.password_hash(password, salt)}"
        for uid, shop in enumerate((None, 1, 2), 1):
            db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                       (uid, f"user{uid}", f"Person {uid}", encoded, shop, 25000))
        db.execute("UPDATE account_profiles SET status='active'")

        def call(method, path, token="", **payload):
            with db:
                return backend.dispatch(db, method, path, {}, payload, "Bearer " + token, at)

        def login(uid):
            return call("POST", "/login", username=f"user{uid}", password=password)["token"]

        def blocked(status, method, path, token, **payload):
            with self.assertRaises(backend.APIError) as result:
                call(method, path, token, **payload)
            self.assertEqual(result.exception.status, status)

        owner, matcha, mixue = map(login, (1, 2, 3))
        self.assertEqual(call("GET", "/me", matcha)["shop_id"], 1)
        blocked(403, "GET", "/employees", matcha)
        blocked(403, "POST", "/employees", mixue)
        created = call("POST", "/employees", owner, username="new-staff", name="New staff",
                       password="new-password", shop_id=1, hourly_rate=26000)
        self.assertTrue(created["id"])
        self.assertEqual(created["status"], "pending")
        blocked(403, "POST", "/login", "", username="new-staff", password="new-password")
        self.assertEqual(len(call("GET", "/employees", owner)), 2)
        call("POST", f"/account-registrations/{created['id']}/approve", owner, hourly_rate=26000)
        self.assertEqual(len(call("GET", "/employees", owner)), 3)
        for shop, staff, other in ((1, matcha, mixue), (2, mixue, matcha)):
            sid = call("POST", "/shifts", owner, shop_id=shop,
                       starts="2026-10-10T17:00:00+07:00", ends="2026-10-10T22:00:00+07:00")["id"]
            blocked(404, "POST", f"/shifts/{sid}/register", other)
            call("POST", f"/shifts/{sid}/register", staff)
            self.assertEqual(call("GET", f"/shifts/{sid}/candidates", owner)[0]["id"], shop + 1)
            call("POST", f"/shifts/{sid}/publish", owner, employee_ids=[shop + 1])
        first = call("GET", "/attendance", matcha)[0]["id"]
        second = call("GET", "/attendance", mixue)[0]["id"]
        at = "2026-10-10T17:12:00+07:00"
        blocked(404, "POST", f"/attendance/{second}/check-in", matcha)
        self.assertTrue(call("POST", f"/attendance/{first}/check-in", matcha)["late"])
        request = call("POST", f"/attendance/{first}/requests", matcha,
                       kind="explanation", reason="Traffic")["id"]
        blocked(403, "POST", f"/requests/{request}/review", matcha, approve=True)
        call("POST", f"/requests/{request}/review", owner, approve=True)
        record = call("GET", "/attendance", matcha)[0]
        self.assertFalse(record["late"])
        self.assertEqual(record["check_in"], at)
        at = "2026-10-10T22:00:00+07:00"
        self.assertEqual(call("POST", f"/attendance/{first}/check-out", matcha)["pay"], 120000)
        request = call("POST", f"/attendance/{second}/requests", mixue,
                       kind="explanation", reason="Absence")["id"]
        call("POST", f"/requests/{request}/review", owner, approve=True)
        self.assertEqual(call("GET", "/attendance", mixue)[0]["status"], "excused_absence")
        backend.open_periods(db, "2026-11-08T23:59:00+07:00")
        self.assertEqual(backend.rows(db, "SELECT * FROM periods"), [])
        at = "2026-11-09T00:00:00+07:00"
        with db:
            backend.open_periods(db, at)
            backend.open_periods(db, at)
        owner, matcha, mixue = map(login, (1, 2, 3))
        notifications = call("GET", "/notifications", matcha)
        self.assertEqual(sum("2026-10." in note["message"] for note in notifications), 1)
        period = "/periods/2026-10"
        blocked(409, "GET", period + "/export", owner)
        blocked(409, "POST", period + "/close", owner)
        request = call("POST", f"/attendance/{second}/requests", mixue, kind="correction",
                       reason="Forgot to punch", check_in="2026-10-10T17:00:00+07:00",
                       check_out="2026-10-10T22:00:00+07:00")["id"]
        blocked(409, "POST", period + "/confirm", mixue)
        call("POST", f"/requests/{request}/review", owner, approve=True)
        self.assertEqual(call("POST", period + "/confirm", mixue)["total_pay"], 125000)
        blocked(409, "POST", period + "/close", owner)
        call("POST", period + "/confirm", matcha)
        self.assertEqual([s["confirmed"] for s in call("GET", period, owner)["shops"]], [1, 1])
        call("POST", period + "/close", owner)
        blocked(409, "POST", f"/attendance/{second}/requests", mixue)
        book = load_workbook(io.BytesIO(call("GET", period + "/export", owner)))
        self.assertEqual(book.sheetnames, ["Đảo Matcha", "Mixue"])
        self.assertEqual([s["J2"].value for s in book], [120000, 125000])


if __name__ == "__main__":
    unittest.main()
