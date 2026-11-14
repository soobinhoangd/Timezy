"""Production entry point for a single persistent SQLite-backed web service."""

import os
from threading import Thread

from backend import app
from backend.wsgi import application
from database.connection import initialize


def bootstrap_owner():
    initialize(app.DB)
    db=app.connect()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            active_owner=db.execute("""SELECT 1 FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                       WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active')""").fetchone()
            if active_owner:
                return
            username=os.environ.get("TIMEZY_ADMIN_USERNAME","").strip()
            password=os.environ.get("TIMEZY_ADMIN_PASSWORD","")
            if not username or len(username)>100 or len(password)<12:
                raise RuntimeError("Set TIMEZY_ADMIN_USERNAME and TIMEZY_ADMIN_PASSWORD (12-256 characters) before first deployment.")
            encoded=app.encode_password(password)
            if db.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone():
                raise RuntimeError("Initial owner username is already in use. Choose another username.")
            uid=db.execute("INSERT INTO users(username,name,password,shop_id) VALUES (?,?,?,NULL)",
                           (username,"Chủ quán",encoded)).lastrowid
            db.execute("INSERT INTO account_profiles(user_id,role,status) VALUES (?,'owner','active')",(uid,))
            db.execute("UPDATE employee_metadata SET joined_on=? WHERE user_id=?",(app.now()[:10],uid))
    finally:
        db.close()


def main():
    from waitress import serve

    bootstrap_owner()
    with app.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        app.open_periods(db,app.now())
    Thread(target=app.notify_loop,daemon=True).start()
    serve(application,host="0.0.0.0",port=int(os.environ.get("PORT","10000")),
          threads=8,max_request_body_size=32768,channel_timeout=30)


if __name__=="__main__":
    main()
