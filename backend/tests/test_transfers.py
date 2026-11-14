import hashlib
import sqlite3
import unittest

from backend import app


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(app.SCHEMA.read_text(encoding="utf-8"))
        self.addCleanup(self.db.close)
        self.at="2026-11-12T12:00:00+07:00"
        for uid,shop in ((1,None),(2,1),(3,1),(4,2),(5,1)):
            self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                            (uid,f"user{uid}",f"Person {uid}","unused",shop,uid*10000))
            self.db.execute("INSERT INTO sessions VALUES (?,?,?)",
                            (hashlib.sha256(f"token{uid}".encode()).hexdigest(),uid,"2027-01-01T00:00:00+07:00"))
        self.db.execute("UPDATE account_profiles SET status='active'")
        self.db.execute("INSERT INTO shifts VALUES (1,1,'2026-11-13T07:30:00+07:00','2026-11-13T12:00:00+07:00',1)")
        # Simulate legacy assignments to verify transfers preserve existing records.
        self.db.execute("DROP TRIGGER one_employee_per_shift_insert")
        self.db.execute("INSERT INTO attendance(id,shift_id,user_id,hourly_rate) VALUES (1,1,2,20000),(2,1,5,50000)")
        self.db.executescript(app.SCHEMA.read_text(encoding="utf-8"))
        self.db.execute("INSERT INTO registrations VALUES (1,2),(1,5)")
        self.db.commit()

    def call(self,path,user=2,method="POST",query=None,**data):
        with self.db:
            return app.dispatch(self.db,method,path,query or {},data,f"Bearer token{user}",self.at)

    def request(self):
        return self.call("/attendance/1/transfer",recipient_id=3)["id"]

    def test_accept_moves_assignment_week_pay_and_notifies_both(self):
        candidates=self.call("/attendance/1/replacements",method="GET")
        self.assertEqual([c["id"] for c in candidates],[3])
        tid=self.request()
        self.assertEqual(self.db.execute("SELECT user_id FROM attendance WHERE id=1").fetchone()[0],2)
        self.assertTrue(self.call("/notifications",3,method="GET"))
        self.assertEqual(len(self.call("/shift-transfers",3,method="GET")),1)
        self.call(f"/shift-transfers/{tid}/respond",3,accept=True)
        # A repeated acceptance must not transfer the same assignment twice.
        self.call(f"/shift-transfers/{tid}/respond",3,accept=True)
        self.assertEqual(self.call("/attendance",2,method="GET"),[])
        recipient=self.call("/attendance",3,method="GET")
        self.assertEqual(recipient[0]["id"],1)
        self.assertEqual(recipient[0]["hourly_rate"],30000)
        self.assertEqual(len(self.call("/attendance",5,method="GET")),1)
        week=self.call("/weekly",3,method="GET",query={"shop_id":["1"],"week":["current"]})
        self.assertEqual({s["user_id"] for s in week["schedule"]},{3,5})
        self.assertFalse(self.db.execute("SELECT 1 FROM registrations WHERE user_id=2").fetchone())
        self.assertTrue(self.db.execute("SELECT 1 FROM registrations WHERE user_id=3").fetchone())
        self.assertTrue(self.call("/notifications",2,method="GET"))
        self.assertTrue(self.call("/notifications",1,method="GET"))

    def test_scope_consent_rejection_and_cancellation(self):
        for user in (1,3,4):
            with self.assertRaises(app.APIError):
                self.call("/attendance/1/transfer",user,recipient_id=3)
        with self.assertRaises(app.APIError):
            self.call("/attendance/1/transfer",recipient_id=4)
        tid=self.request()
        with self.assertRaises(app.APIError):
            self.request()
        for user in (1,2,4):
            with self.assertRaises(app.APIError):
                self.call(f"/shift-transfers/{tid}/respond",user,accept=True)
        self.call(f"/shift-transfers/{tid}/respond",3,accept=False)
        self.assertEqual(self.db.execute("SELECT user_id FROM attendance WHERE id=1").fetchone()[0],2)
        tid=self.request()
        self.call(f"/shift-transfers/{tid}/cancel")
        with self.assertRaises(app.APIError):
            self.call(f"/shift-transfers/{tid}/respond",3,accept=True)

    def test_rechecks_overlap_and_start_time_on_accept(self):
        tid=self.request()
        self.db.execute("INSERT INTO shifts VALUES (2,1,'2026-11-13T10:00:00+07:00','2026-11-13T18:00:00+07:00',1)")
        self.db.execute("INSERT INTO attendance(shift_id,user_id,hourly_rate) VALUES (2,3,30000)")
        self.db.commit()
        with self.assertRaises(app.APIError) as error:
            self.call(f"/shift-transfers/{tid}/respond",3,accept=True)
        self.assertEqual(error.exception.status,409)
        self.assertEqual(self.db.execute("SELECT user_id FROM attendance WHERE id=1").fetchone()[0],2)
        self.call(f"/shift-transfers/{tid}/respond",3,accept=False)
        self.db.execute("DELETE FROM attendance WHERE shift_id=2")
        self.db.commit()
        tid=self.request()
        self.at="2026-11-13T07:30:00+07:00"
        with self.assertRaises(app.APIError):
            self.call(f"/shift-transfers/{tid}/respond",3,accept=True)
        self.assertEqual(self.call("/shift-transfers",3,method="GET")[0]["display_status"],"expired")

    def test_reschedule_cancels_request_and_retains_history(self):
        tid=self.request()
        self.call("/shifts/1/reschedule",1,starts="2026-11-14T07:30:00+07:00",
                  ends="2026-11-14T12:00:00+07:00")
        request=self.call("/shift-transfers",3,method="GET")[0]
        self.assertEqual(request["id"],tid)
        self.assertEqual(request["status"],"cancelled")
        self.assertIsNone(request["attendance_id"])


if __name__=="__main__":
    unittest.main()
