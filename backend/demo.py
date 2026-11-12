"""Run a local demo with a separate SQLite database."""

import secrets
from datetime import timedelta
from pathlib import Path

from backend import app
from database.connection import initialize

DEMO_DB = Path(__file__).resolve().parents[1] / "database" / "data" / "demo.sqlite3"
PASSWORD = "TimezyDemo123"


def seed():
    initialize(DEMO_DB)
    db = app.connect_database(DEMO_DB)
    try:
        with db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
            accounts = [
                ("owner", "Chủ quán demo", None),
                ("matcha01", "Nguyễn Minh Anh", 1),
                ("matcha02", "Trần Gia Huy", 1),
                ("mixue01", "Lê Thảo Vy", 2),
                ("mixue02", "Phạm Hoàng Nam", 2),
            ]
            for username, name, shop in accounts:
                salt = secrets.token_hex(16)
                db.execute("INSERT INTO users(username,name,password,shop_id,hourly_rate) VALUES (?,?,?,?,?)",
                           (username, name, f"{salt}:{app.password_hash(PASSWORD, salt)}", shop, 25000))
            # Demo fixtures represent employees already approved by the demo owner.
            db.execute("UPDATE account_profiles SET status='active' WHERE role='employee'")
            current = app.datetime.now(app.VN).replace(microsecond=0)
            last_month = current.replace(day=1) - timedelta(days=1)
            for branch, employees in ((1, (2, 3)), (2, (4, 5))):
                # A current assigned shift lets an employee check in immediately.
                starts, ends = current - timedelta(minutes=10), current + timedelta(hours=3)
                sid = db.execute("INSERT INTO shifts(shop_id,starts,ends,published) VALUES (?,?,?,1)",
                                 (branch, app.timestamp(starts), app.timestamp(ends))).lastrowid
                for employee in employees:
                    db.execute("INSERT INTO registrations VALUES (?,?)", (sid, employee))
                    db.execute("INSERT INTO attendance(shift_id,user_id,hourly_rate) VALUES (?,?,25000)",
                               (sid, employee))
                # An open slot contains candidates so owners can try publishing.
                starts = (current + timedelta(days=1)).replace(hour=17, minute=0, second=0)
                sid = db.execute("INSERT INTO shifts(shop_id,starts,ends) VALUES (?,?,?)",
                                 (branch, app.timestamp(starts), app.timestamp(starts + timedelta(hours=5)))).lastrowid
                for employee in employees:
                    db.execute("INSERT INTO registrations VALUES (?,?)", (sid, employee))
                # A previous-month period contains both normal and missing punches.
                starts = last_month.replace(day=15, hour=17, minute=0, second=0)
                ends = starts + timedelta(hours=5)
                sid = db.execute("INSERT INTO shifts(shop_id,starts,ends,published) VALUES (?,?,?,1)",
                                 (branch, app.timestamp(starts), app.timestamp(ends))).lastrowid
                for index, employee in enumerate(employees):
                    aid = db.execute("""INSERT INTO attendance(shift_id,user_id,hourly_rate,check_in,check_out)
                                        VALUES (?,?,25000,?,?)""",
                                     (sid, employee, app.timestamp(starts),
                                      app.timestamp(ends) if index == 0 else None)).lastrowid
                    if index == 1:
                        db.execute("""INSERT INTO requests(attendance_id,kind,reason,proposed_in,proposed_out,created)
                                      VALUES (?,'correction',?,?,?,?)""",
                                   (aid, "Em quên chấm giờ ra sau khi dọn quầy.",
                                    app.timestamp(starts), app.timestamp(ends), app.now()))
            app.open_periods(db, app.now())
            for employee in (2, 3, 4, 5):
                app.notify(db, employee, "Lịch demo đã sẵn sàng. Bạn có thể thử chấm công và xem bảng công.", app.now())
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    app.DB = str(DEMO_DB)
    import sys

    sys.argv = [sys.argv[0], "serve", "--host", "127.0.0.1", "--port", "8000"]
    app.main()
