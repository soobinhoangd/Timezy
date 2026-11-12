import sqlite3
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
SCHEMA = DIRECTORY / "schema.sql"
DEFAULT_DB = DIRECTORY / "data" / "timezy.sqlite3"


def connect(path):
    if str(path) != ":memory:":
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path):
    db = connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA.read_text(encoding="utf-8"))
        if db.execute("PRAGMA user_version").fetchone()[0] < 6:
            db.execute("""INSERT OR IGNORE INTO weekly_submissions(user_id,week_start,confirmed_at)
                          SELECT user_id,date(day,'weekday 0','-6 days'),strftime('%Y-%m-%dT%H:%M:%S+00:00','now')
                          FROM weekly_availability GROUP BY user_id,date(day,'weekday 0','-6 days')""")
        db.execute("""INSERT OR IGNORE INTO account_profiles(user_id,role,status)
                      SELECT id,CASE WHEN shop_id IS NULL THEN 'owner' ELSE 'employee' END,
                      'active' FROM users""")
        db.execute("PRAGMA user_version=6")
        db.commit()
    finally:
        db.close()
