import sqlite3
import unittest
import hashlib

from backend import app


class WeeklyTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(app.SCHEMA.read_text(encoding="utf-8"))
        self.addCleanup(self.db.close)
        self.at="2026-11-12T12:00:00+07:00"
        for uid,shop in ((1,None),(2,1),(3,1),(4,2)):
            self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,25000)",
                            (uid,f"user{uid}",f"Person {uid}","unused",shop))
            token=hashlib.sha256(f"token{uid}".encode()).hexdigest()
            self.db.execute("INSERT INTO sessions VALUES (?,?,?)",(token,uid,"2027-01-01T00:00:00+07:00"))
        self.db.execute("UPDATE account_profiles SET status='active'")
        self.db.commit()

    def call(self,path,user=1,method="POST",query=None,**data):
        with self.db:
            return app.dispatch(self.db,method,path,query or {},data,f"Bearer token{user}",self.at)

    def week(self,user=1,week="next",shop=1):
        return self.call("/weekly",user,method="GET",query={"week":[week],"shop_id":[str(shop)]})

    def tick(self,user,slot,checked=True):
        week=self.week(user)
        selected={(cell["day"],cell["slot"]) for cell in week["cells"] if cell["registered"]}
        if checked:
            selected.add(("2026-11-16",slot))
        else:
            selected.discard(("2026-11-16",slot))
        return self.call("/weekly/confirm",user,week_start=week["days"][0],
                         revision=week["submission"]["revision"] if week["submission"] else 0,
                         slots=[dict(day=day,slot=chosen) for day,chosen in selected])

    def test_only_confirmed_choices_are_visible_and_stale_edits_fail(self):
        self.db.execute("INSERT INTO weekly_availability VALUES (2,'2026-11-16','morning')")
        self.db.commit()
        self.assertFalse(any(cell["candidates"] for cell in self.week()["cells"]))
        self.configure()
        with self.assertRaises(app.APIError):
            self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="morning",employee_ids=[2])
        self.call("/weekly/confirm",2,week_start="2026-11-16",revision=0,
                  slots=[dict(day="2026-11-16",slot="morning")])
        with self.assertRaises(app.APIError) as error:
            self.call("/weekly/confirm",2,week_start="2026-11-16",revision=0,slots=[])
        self.assertEqual(error.exception.status,409)
        self.assertTrue(any(cell["candidates"] for cell in self.week()["cells"]))
        self.call("/weekly/confirm",2,week_start="2026-11-16",revision=1,slots=[])
        self.assertFalse(any(cell["candidates"] for cell in self.week()["cells"]))
        self.assertIsNotNone(self.week(2)["submission"])
        with self.assertRaises(app.APIError):
            self.call("/weekly/availability",2,day="2026-11-16",slot="morning",checked=True)

    def configure(self):
        values=[("morning","07:30","12:00"),("afternoon","12:00","18:00"),
                ("evening","18:00","23:30"),("split","20:00","23:30")]
        self.call("/weekly/settings",shop_id=1,templates=[dict(slot=s,starts=a,ends=b) for s,a,b in values])

    def test_registration_shop_scope_publish_and_shared_schedule(self):
        self.assertEqual(len(self.week()["cells"]),28)
        self.assertEqual(self.week()["days"][0],"2026-11-16")
        self.assertEqual(len(self.week(2,"current")["employees"]),2)
        with self.assertRaises(app.APIError):
            self.week(2,shop=2)
        self.tick(2,"morning")
        self.tick(3,"morning")
        self.tick(3,"morning",False)
        cell=next(c for c in self.week()["cells"] if c["day"]=="2026-11-16" and c["slot"]=="morning")
        self.assertEqual([c["id"] for c in cell["candidates"]],[2])
        self.assertTrue(next(c for c in self.week(2)["cells"] if c["day"]=="2026-11-16" and c["slot"]=="morning")["registered"])
        self.assertEqual(next(t for t in self.week()["templates"] if t["slot"]=="morning")["starts"],"07:30")
        self.assertEqual(next(t for t in self.week()["templates"] if t["slot"]=="split")["ends"],"23:30")
        self.configure()
        with self.assertRaises(app.APIError):
            self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="morning",employee_ids=[4])
        self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="morning",employee_ids=[2])
        with self.assertRaises(app.APIError):
            self.tick(2,"morning",False)
        with self.assertRaises(app.APIError):
            self.call("/weekly/availability",2,day="2026-11-12",slot="morning",checked=True)
        self.at="2026-11-16T07:00:00+07:00"
        week=self.week(3,"current")
        self.assertEqual(week["schedule"][0]["user_id"],2)
        self.assertNotIn("hourly_rate",week["schedule"][0])
        self.assertEqual(week["days"][-1],"2026-11-22")

    def test_overlapping_full_and_split_cannot_be_assigned_together(self):
        self.configure()
        self.tick(2,"evening")
        self.tick(2,"split")
        self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="evening",employee_ids=[2])
        count=self.db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
        with self.assertRaises(app.APIError) as error:
            self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="split",employee_ids=[2])
        self.assertEqual(error.exception.status,409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0],count)

    def test_exactly_one_employee_per_slot(self):
        self.tick(2,"morning")
        self.tick(3,"morning")
        with self.assertRaises(app.APIError):
            self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="morning",employee_ids=[2,3])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0],0)
        self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="morning",employee_ids=[2])
        self.tick(2,"evening")
        self.tick(3,"split")
        self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="evening",employee_ids=[2])
        self.call("/weekly/publish",shop_id=1,day="2026-11-16",slot="split",employee_ids=[3])
        assigned=self.db.execute("""SELECT w.slot,COUNT(*) AS count FROM weekly_slots w
                                   JOIN attendance a ON a.shift_id=w.shift_id GROUP BY w.slot""").fetchall()
        self.assertEqual({row["slot"]:row["count"] for row in assigned},{"morning":1,"evening":1,"split":1})
        sid=self.call("/shifts",shop_id=1,starts="2026-11-16T07:45:00+07:00",
                      ends="2026-11-16T12:00:00+07:00")["id"]
        self.call(f"/shifts/{sid}/register",3)
        with self.assertRaises(app.APIError) as error:
            self.call(f"/shifts/{sid}/publish",employee_ids=[3])
        self.assertEqual(error.exception.status,409)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db:
                self.db.execute("INSERT INTO attendance(shift_id,user_id,hourly_rate) VALUES (?,3,25000)",
                                (self.db.execute("SELECT shift_id FROM weekly_slots WHERE slot='morning'").fetchone()[0],))


if __name__=="__main__":
    unittest.main()
