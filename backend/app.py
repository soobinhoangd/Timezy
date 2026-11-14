import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from getpass import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from openpyxl import Workbook
from backend.weekly import WeeklyError, handle_weekly
from backend.transfers import TransferError, handle_transfers
from backend.capacity import position_occupied
from backend.profiles import ProfileError, profile_info, update_profile, update_avatar
from database.connection import DEFAULT_DB, SCHEMA, connect as connect_database, initialize

VN = timezone(timedelta(hours=7))
DB = os.environ.get("TIMEZY_DB", str(DEFAULT_DB))
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
STATIC_ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/attendance-state.js": ("attendance-state.js", "text/javascript; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/styles.css": ("styles.css", "text/css; charset=utf-8")}
MONTH = r"\d{4}-(?:0[1-9]|1[0-2])"


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def require(condition, message, status=400):
    if not condition:
        raise APIError(status, message)


def timestamp(value):
    return value.astimezone(VN).isoformat(timespec="seconds")


def now():
    return timestamp(datetime.now(VN))


def parse_time(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError()
        return timestamp(result)
    except (TypeError, ValueError, OverflowError):
        raise APIError(400, "Giờ phải ở dạng ISO 8601 và có múi giờ.") from None


def connect():
    return connect_database(DB)


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def encode_password(password):
    require(isinstance(password, str) and 8 <= len(password) <= 256,
            "Mật khẩu cần từ 8 đến 256 ký tự.")
    salt = secrets.token_hex(16)
    return f"{salt}:{password_hash(password, salt)}"


def matches_password(account, password):
    salt, expected = account["password"].split(":") if account else ("00" * 16, "00" * 64)
    return hmac.compare_digest(password_hash(password, salt), expected)


def recovery_code(db, uid):
    code = secrets.token_urlsafe(24)
    hashed = hashlib.sha256(code.encode()).hexdigest()
    db.execute("UPDATE account_profiles SET recovery_hash=? WHERE user_id=?", (hashed, uid))
    return code


def rows(db, sql, *args):
    return [dict(row) for row in db.execute(sql, args)]


def one(db, sql, *args):
    return db.execute(sql, args).fetchone()


def notify(db, user, message, at):
    db.execute("INSERT INTO notifications(user_id,message,created) VALUES (?,?,?)",
               (user, message, at))


def open_periods(db, at):
    today = date.fromisoformat(at[:10])
    latest = today.replace(day=1) - timedelta(days=1)
    if today.day < 9:
        latest = latest.replace(day=1) - timedelta(days=1)
    for item in rows(db, """SELECT DISTINCT substr(s.starts,1,7) AS month
                            FROM shifts s JOIN attendance a ON a.shift_id=s.id
                            WHERE s.published=1 AND substr(s.starts,1,7)<=?""", latest.strftime("%Y-%m")):
        month = item["month"]
        if not db.execute("INSERT OR IGNORE INTO periods(month,opened) VALUES (?,?)",
                          (month, at)).rowcount:
            continue
        staff = rows(db, """SELECT DISTINCT a.user_id FROM attendance a JOIN shifts s ON s.id=a.shift_id
                            WHERE s.published=1 AND substr(s.starts,1,7)=?""", month)
        for employee in staff:
            uid = employee["user_id"]
            db.execute("INSERT INTO statements(month,user_id) VALUES (?,?)", (month, uid))
            notify(db, uid, f"Xác nhận bảng công và lương tháng {month}.", at)


def notify_loop():
    import time

    while True:
        try:
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                open_periods(db, now())
                db.execute("DELETE FROM sessions WHERE expires<=?", (now(),))
                db.commit()
        except sqlite3.Error as error:
            print(f"Tác vụ kỳ công sẽ thử lại: {error}", flush=True)
        time.sleep(30)


ATTENDANCE = """
SELECT a.*, s.shop_id, s.starts, s.ends, s.published, u.name
 ,EXISTS(SELECT 1 FROM periods p WHERE p.month=substr(s.starts,1,7) AND p.closed IS NOT NULL) AS closed
FROM attendance a JOIN shifts s ON s.id=a.shift_id JOIN users u ON u.id=a.user_id
"""


def summarize(record, at):
    entry, exit_ = record["check_in"], record["check_out"]
    late = bool(entry and entry > record["starts"] and not record["excused"])
    absent = not entry and at >= record["ends"]
    if absent:
        state = "excused_absence" if record["excused"] else "absent"
    elif not entry:
        state = "not_checked_in"
    elif exit_:
        state = "completed"
    else:
        state = "missing_checkout" if at > record["ends"] else "working"
    seconds = 0
    if entry and exit_:
        seconds = int((datetime.fromisoformat(exit_) - datetime.fromisoformat(entry)).total_seconds())
    return dict(record, status=state, late=late, seconds_worked=seconds,
                pay=(seconds * record["hourly_rate"] + 1800) // 3600)


def mutable_month(db, month):
    require(not one(db, "SELECT 1 FROM periods WHERE month=? AND closed IS NOT NULL", month),
            "Kỳ công đã chốt.", 409)


def invalidate_confirmation(db, month, uid):
    db.execute("UPDATE statements SET confirmed=NULL WHERE month=? AND user_id=?", (month, uid))


def statement(db, month, uid, at):
    item = one(db, "SELECT * FROM statements WHERE month=? AND user_id=?", month, uid)
    require(item, "Không tìm thấy bảng công cá nhân.", 404)
    records = rows(db, ATTENDANCE + """
        WHERE s.published=1 AND substr(s.starts,1,7)=? AND a.user_id=? ORDER BY s.starts""", month, uid)
    entries = [summarize(record, at) for record in records]
    closed = one(db, "SELECT closed FROM periods WHERE month=?", month)["closed"]
    return dict(item, closed=closed, entries=entries, total_seconds=sum(x["seconds_worked"] for x in entries),
                total_pay=sum(x["pay"] for x in entries))


def pending(db, month, uid=None):
    return one(db, """SELECT 1 FROM requests r JOIN attendance a ON a.id=r.attendance_id
                      JOIN shifts s ON s.id=a.shift_id
                      WHERE r.status='pending' AND substr(s.starts,1,7)=?
                        AND (? IS NULL OR a.user_id=?) LIMIT 1""", month, uid, uid)


def excel(db, month, at):
    book = Workbook()
    book.remove(book.active)
    for shop in rows(db, "SELECT * FROM shops ORDER BY id"):
        sheet = book.create_sheet(shop["name"])
        sheet.append(["Mã nhân viên", "Nhân viên", "Bắt đầu ca", "Kết thúc ca",
                      "Giờ vào", "Giờ ra", "Trạng thái", "Đi muộn", "Giờ công", "Tiền công (đ)"])
        statuses = {"completed": "Đã chấm công", "absent": "Bỏ ca", "excused_absence": "Vắng có lý do"}
        for record in rows(db, ATTENDANCE + """
            WHERE s.shop_id=? AND s.published=1 AND substr(s.starts,1,7)=?
            ORDER BY u.name,s.starts""", shop["id"], month):
            entry = summarize(record, at)
            sheet.append([entry["user_id"], entry["name"], entry["starts"], entry["ends"],
                          entry["check_in"], entry["check_out"], statuses[entry["status"]],
                          "Có" if entry["late"] else "Không", entry["seconds_worked"] / 3600, entry["pay"]])
            sheet.cell(sheet.max_row, 2).data_type = "s"
            sheet.cell(sheet.max_row, 9).number_format = "0.00"
        sheet.freeze_panes = "C2"
        sheet.auto_filter.ref = sheet.dimensions
        for column, width in zip("ABCDEFGHIJ", [16, 25, 30, 30, 30, 30, 20, 14, 14, 18]):
            sheet.column_dimensions[column].width = width
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def string(data, key, limit=1000):
    value = data.get(key)
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, f"Trường {key} không hợp lệ.")
    return value.strip()


def dispatch(db, method, path, query, data, auth, at):
    if method == "GET" and path == "/health":
        return {"ok": True}
    if method == "GET" and path == "/clock":
        return {"now": at, "timezone": "Asia/Ho_Chi_Minh"}
    if method == "POST" and path == "/signup":
        username = string(data, "username", 100)
        name = string(data, "name", 100) if "name" in data else username
        birth_date = string(data, "birth_date", 10)
        try:
            born = date.fromisoformat(birth_date)
            require(born.isoformat() == birth_date and born < date.fromisoformat(at[:10]),
                    "Ngày sinh phải hợp lệ và trước ngày hiện tại.")
        except ValueError:
            raise APIError(400, "Ngày sinh không hợp lệ.") from None
        gender = data.get("gender")
        require(gender in ("male", "female", "other"), "Hãy chọn giới tính.")
        email = string(data, "email", 254).lower()
        require(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email), "Email không hợp lệ.")
        phone = re.sub(r"[\s().-]", "", string(data, "phone", 30))
        if phone.startswith("0"):
            phone = "+84" + phone[1:]
        require(re.fullmatch(r"\+?[1-9][0-9]{8,14}", phone), "Số điện thoại không hợp lệ.")
        require(data.get("password") == data.get("confirm_password"), "Hai mật khẩu chưa khớp.")
        role, branch = data.get("role"), data.get("shop_id")
        require(role in ("owner", "employee"), "Vai trò không hợp lệ.")
        if role == "employee":
            require(type(branch) is int and branch in (1, 2), "Hãy chọn cơ sở làm việc.")
        else:
            branch = None
        encoded = encode_password(data.get("password"))
        require(not one(db, "SELECT 1 FROM users WHERE username=?", username),
                "Tên đăng nhập đã được sử dụng.", 409)
        require(not one(db, "SELECT 1 FROM account_details WHERE email=? OR phone=?", email, phone),
                "Email hoặc số điện thoại đã được sử dụng.", 409)
        first_owner = role == "owner" and not one(db, "SELECT 1 FROM users WHERE shop_id IS NULL")
        status = "active" if first_owner else "pending"
        uid = db.execute("INSERT INTO users(username,name,password,shop_id) VALUES (?,?,?,?)",
                         (username, name, encoded, branch)).lastrowid
        db.execute("""INSERT INTO account_profiles(user_id,role,status) VALUES (?,?,?)
                      ON CONFLICT(user_id) DO UPDATE SET role=excluded.role,status=excluded.status""",
                   (uid, role, status))
        db.execute("INSERT INTO account_details VALUES (?,?,?,?,?)",
                   (uid, birth_date, gender, email, phone))
        if first_owner:
            db.execute("UPDATE employee_metadata SET joined_on=? WHERE user_id=?",(at[:10],uid))
        code = recovery_code(db, uid)
        for admin in rows(db, """SELECT u.id FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active') AND u.id<>?""", uid):
            notify(db, admin["id"], f"{name} đăng ký tài khoản mới và đang chờ duyệt.", at)
        return {"status": status, "recovery_code": code}
    if method == "POST" and path == "/reset-password":
        username = string(data, "username", 100)
        code = string(data, "recovery_code", 200)
        encoded = encode_password(data.get("new_password"))
        account = one(db, """SELECT u.id,p.recovery_hash FROM users u
                            JOIN account_profiles p ON p.user_id=u.id WHERE u.username=?""", username)
        expected = account["recovery_hash"] if account and account["recovery_hash"] else "0" * 64
        require(hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), expected),
                "Tên đăng nhập hoặc mã khôi phục không đúng.", 400)
        db.execute("UPDATE users SET password=? WHERE id=?", (encoded, account["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=?", (account["id"],))
        return {"ok": True, "recovery_code": recovery_code(db, account["id"])}

    if method == "POST" and path == "/login":
        username = string(data, "username", 100)
        password = data.get("password")
        require(isinstance(password, str) and 0 < len(password) <= 256, "Mật khẩu không hợp lệ.")
        account = one(db, "SELECT * FROM users WHERE username=?", username)
        valid = matches_password(account, password)
        require(account and valid, "Sai tên đăng nhập hoặc mật khẩu.", 401)
        profile = one(db, "SELECT * FROM account_profiles WHERE user_id=?", account["id"])
        require(not profile or profile["status"] == "active", "Tài khoản đang chờ chủ quán duyệt.", 403)
        remember = data.get("remember", False)
        require(type(remember) is bool, "Trường remember phải là true hoặc false.")
        token = secrets.token_urlsafe(32)
        expires = timestamp(datetime.fromisoformat(at) + (timedelta(days=30) if remember else timedelta(hours=12)))
        db.execute("INSERT INTO sessions VALUES (?,?,?)",
                   (hashlib.sha256(token.encode()).hexdigest(), account["id"], expires))
        return {"token": token, "expires": expires, "shop_id": account["shop_id"],
                "role": "owner" if account["shop_id"] is None else "employee"}

    require(auth.startswith("Bearer "), "Cần đăng nhập.", 401)
    digest = hashlib.sha256(auth[7:].encode()).hexdigest()
    actor = one(db, """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                      WHERE s.token=? AND s.expires>?""", digest, at)
    require(actor, "Phiên đăng nhập không hợp lệ.", 401)
    profile = one(db, "SELECT * FROM account_profiles WHERE user_id=?", actor["id"])
    require(not profile or profile["status"] == "active", "Tài khoản chưa được kích hoạt.", 403)
    uid, shop = actor["id"], actor["shop_id"]
    owner = shop is None
    if path=="/shift-transfers" or path.startswith("/shift-transfers/") or re.fullmatch(r"/attendance/\d+/(replacements|transfer)",path):
        try:
            return handle_transfers(db,method,path,data,actor,at)
        except TransferError as error:
            raise APIError(error.status,error.message) from None
    if path == "/weekly" or path.startswith("/weekly/"):
        try:
            return handle_weekly(db,method,path,query,data,actor,at,
                lambda sid, selected: dispatch(db,"POST",f"/shifts/{sid}/publish",{},
                                              {"employee_ids":selected},auth,at))
        except WeeklyError as error:
            raise APIError(error.status,error.message) from None
    if method == "POST" and path in ("/change-password", "/recovery-code"):
        password = data.get("current_password")
        require(isinstance(password, str) and 0 < len(password) <= 256, "Nhập mật khẩu hiện tại.")
        require(matches_password(actor, password), "Mật khẩu hiện tại không đúng.")
        if path == "/change-password":
            encoded = encode_password(data.get("new_password"))
            require(data["new_password"] != password, "Mật khẩu mới cần khác mật khẩu hiện tại.")
            db.execute("UPDATE users SET password=? WHERE id=?", (encoded, uid))
            db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            return {"ok": True}
        db.execute("INSERT OR IGNORE INTO account_profiles VALUES (?,?, 'active',NULL)",
                   (uid, "owner" if owner else "employee"))
        return {"recovery_code": recovery_code(db, uid)}
    if method == "GET" and path == "/account-registrations":
        require(owner, "Chỉ chủ quán có quyền xem tài khoản chờ duyệt.", 403)
        return rows(db, """SELECT u.id,u.username,u.name,u.shop_id,u.hourly_rate,p.role FROM users u
                           JOIN account_profiles p ON p.user_id=u.id WHERE p.status='pending'""")
    approval = re.fullmatch(r"/account-registrations/(\d+)/approve", path)
    if method == "POST" and approval:
        require(owner, "Chỉ chủ quán có quyền duyệt tài khoản.", 403)
        pending_user = one(db, "SELECT * FROM account_profiles WHERE user_id=? AND status='pending'", int(approval[1]))
        require(pending_user, "Không tìm thấy tài khoản chờ duyệt.", 404)
        rate = data.get("hourly_rate", 0)
        require(type(rate) is int and 0 <= rate <= 10000000, "Đơn giá không hợp lệ.")
        db.execute("UPDATE account_profiles SET status='active' WHERE user_id=?", (int(approval[1]),))
        db.execute("UPDATE users SET hourly_rate=? WHERE id=?", (rate, int(approval[1])))
        db.execute("UPDATE employee_metadata SET joined_on=COALESCE(joined_on,?) WHERE user_id=?",
                   (at[:10],int(approval[1])))
        notify(db, int(approval[1]), "Tài khoản của bạn đã được duyệt.", at)
        return {"ok": True}
    if path == "/me" and method == "GET":
        return profile_info(db,uid)
    if path in ("/me/profile","/me/avatar") and method=="POST":
        try:
            return update_profile(db,uid,data,at) if path=="/me/profile" else update_avatar(db,uid,data)
        except ProfileError as error:
            raise APIError(error.status,error.message) from None
    if path == "/employees" and method == "GET":
        require(owner, "Chỉ chủ quán xem danh sách nhân viên.", 403)
        return rows(db, """SELECT u.id,u.name,u.username,u.shop_id,u.hourly_rate FROM users u
                           LEFT JOIN account_profiles p ON p.user_id=u.id
                           WHERE u.shop_id IS NOT NULL AND (p.status IS NULL OR p.status='active')
                           ORDER BY u.shop_id,u.name""")
    if path == "/employees" and method == "POST":
        require(owner, "Chỉ chủ quán tạo nhân viên.", 403)
        username = string(data, "username", 100)
        name = string(data, "name", 100)
        password = data.get("password")
        branch, rate = data.get("shop_id"), data.get("hourly_rate")
        require(type(branch) is int and branch in (1, 2), "Cơ sở không hợp lệ.")
        require(type(rate) is int and 0 <= rate <= 10000000, "Đơn giá không hợp lệ.")
        require(isinstance(password, str) and 8 <= len(password) <= 256,
                "Mật khẩu cần từ 8 đến 256 ký tự.")
        salt = secrets.token_hex(16)
        employee = db.execute("INSERT INTO users(username,name,password,shop_id,hourly_rate) VALUES (?,?,?,?,?)",
                             (username, name, f"{salt}:{password_hash(password,salt)}", branch, rate)).lastrowid
        for admin in rows(db, """SELECT u.id FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active')"""):
            notify(db, admin["id"], f"Nhân viên {name} vừa được tạo và đang chờ duyệt.", at)
        return {"id": employee, "status": "pending"}
    if path == "/logout" and method == "POST":
        db.execute("DELETE FROM sessions WHERE token=?", (digest,))
        return {"ok": True}
    if path == "/notifications" and method == "GET":
        return rows(db, "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", uid)
    if path == "/shops" and method == "GET":
        return rows(db, "SELECT * FROM shops WHERE ? IS NULL OR id=?", shop, shop)
    if path == "/schedule-issues" and method == "POST":
        require(not owner, "Chỉ nhân viên có thể báo chưa có ca.", 403)
        reason = string(data, "reason")
        for admin in rows(db, "SELECT id FROM users WHERE shop_id IS NULL"):
            branch = one(db, "SELECT name FROM shops WHERE id=?", shop)["name"]
            notify(db, admin["id"], f"{actor['name']} ({branch}) báo chưa có ca: {reason}", at)
        return {"ok": True}

    if path == "/shifts" and method == "GET":
        return rows(db, """SELECT s.*, EXISTS(SELECT 1 FROM registrations r
                           WHERE r.shift_id=s.id AND r.user_id=?) AS registered,
                           EXISTS(SELECT 1 FROM attendance a
                           WHERE a.shift_id=s.id AND a.user_id=?) AS assigned
                           FROM shifts s WHERE (? IS NULL OR s.shop_id=?)
                           ORDER BY s.starts DESC""", uid, uid, shop, shop)
    if path == "/shifts" and method == "POST":
        require(owner, "Chỉ chủ quán có quyền mở ca đăng ký.", 403)
        branch = data.get("shop_id")
        require(type(branch) is int and branch in (1, 2), "Cơ sở không hợp lệ.")
        starts, ends = parse_time(data.get("starts")), parse_time(data.get("ends"))
        require(ends > starts > at, "Ca phải bắt đầu trong tương lai và kết thúc sau giờ bắt đầu.")
        sid = db.execute("INSERT INTO shifts(shop_id,starts,ends) VALUES (?,?,?)",
                         (branch, starts, ends)).lastrowid
        return {"id": sid}

    match = re.fullmatch(r"/shifts/(\d+)/(register|candidates|publish|reschedule)", path)
    if match:
        sid, action = int(match[1]), match[2]
        shift = one(db, "SELECT * FROM shifts WHERE id=? AND (? IS NULL OR shop_id=?)", sid, shop, shop)
        require(shift, "Không tìm thấy ca.", 404)
        if action == "register" and method == "POST":
            require(not owner, "Chỉ nhân viên có quyền đăng ký.", 403)
            require(not shift["published"] and shift["starts"] > at, "Ca đã đóng đăng ký.", 409)
            db.execute("INSERT OR IGNORE INTO registrations VALUES (?,?)", (sid, uid))
            return {"ok": True}
        require(owner, "Chỉ chủ quán có quyền xếp ca.", 403)
        if action == "reschedule" and method == "POST":
            starts, ends = parse_time(data.get("starts")), parse_time(data.get("ends"))
            require(ends > starts > at, "Ca phải bắt đầu trong tương lai và kết thúc sau giờ bắt đầu.")
            require(shift["starts"] > at and not one(db, """SELECT 1 FROM attendance
                        WHERE shift_id=? AND check_in IS NOT NULL""", sid),
                    "Không thể đổi giờ khi ca đã bắt đầu hoặc đã có người check-in.", 409)
            if (starts, ends) == (shift["starts"], shift["ends"]):
                return dict(shift)
            for employee in rows(db, "SELECT user_id FROM registrations WHERE shift_id=?", sid):
                notify(db, employee["user_id"], f"Ca {shift['starts']} đã đổi sang {starts}. Hãy đăng ký lại.", at)
            for transfer in rows(db,"SELECT recipient_id FROM shift_transfers WHERE shift_id=? AND status='pending'",sid):
                notify(db,transfer["recipient_id"],"Yêu cầu thay ca đã hủy vì chủ quán đổi giờ ca.",at)
            db.execute("UPDATE shift_transfers SET status='cancelled',responded=? WHERE shift_id=? AND status='pending'",
                       (at,sid))
            db.execute("DELETE FROM attendance WHERE shift_id=?", (sid,))
            db.execute("DELETE FROM registrations WHERE shift_id=?", (sid,))
            db.execute("UPDATE shifts SET starts=?,ends=?,published=0 WHERE id=?", (starts, ends, sid))
            return dict(one(db, "SELECT * FROM shifts WHERE id=?", sid))
        if action == "candidates" and method == "GET":
            return rows(db, """SELECT u.id,u.name FROM registrations r JOIN users u ON u.id=r.user_id
                               WHERE r.shift_id=? AND u.shop_id=? ORDER BY u.name""", sid, shift["shop_id"])
        if action == "publish" and method == "POST":
            require(not shift["published"] and shift["starts"] > at, "Ca đã công bố hoặc đã bắt đầu.", 409)
            selected = data.get("employee_ids")
            require(isinstance(selected, list) and len(selected)==1 and
                    type(selected[0]) is int and selected[0]>0, "Mỗi ca chỉ được xếp đúng một nhân viên.")
            require(not one(db,"SELECT 1 FROM attendance WHERE shift_id=?",sid),
                    "Ca đã có nhân viên được xếp.",409)
            require(not position_occupied(db,shift),
                    "Vị trí ca này trong ngày đã có nhân viên ở một lịch khác.",409)
            for employee in set(selected):
                candidate = one(db, """SELECT u.hourly_rate FROM registrations r JOIN users u ON u.id=r.user_id
                                       WHERE r.shift_id=? AND r.user_id=? AND u.shop_id=?""",
                                sid, employee, shift["shop_id"])
                require(candidate, "Chỉ chọn được nhân viên đã đăng ký đúng ca.")
                conflict = one(db, ATTENDANCE + """ WHERE a.user_id=? AND s.published=1
                                                    AND s.starts<? AND s.ends>?""",
                               employee, shift["ends"], shift["starts"])
                require(not conflict, "Nhân viên đã có ca trùng giờ.", 409)
                db.execute("INSERT INTO attendance(shift_id,user_id,hourly_rate) VALUES (?,?,?)",
                           (sid, employee, candidate["hourly_rate"]))
                notify(db, employee, f"Đã xếp ca bắt đầu lúc {shift['starts']}.", at)
            db.execute("UPDATE shifts SET published=1 WHERE id=?", (sid,))
            return {"ok": True}

    if path == "/attendance" and method == "GET":
        day = query.get("day", [None])[0]
        branch = query.get("shop_id", [None])[0]
        require(branch in (None, "1", "2"), "Cơ sở không hợp lệ.")
        if day is not None:
            try:
                require(date.fromisoformat(day).isoformat() == day, "Ngày không hợp lệ.")
            except ValueError:
                raise APIError(400, "Ngày không hợp lệ.") from None
        records = rows(db, ATTENDANCE + """ WHERE s.published=1 AND (? OR a.user_id=?)
                    AND (? IS NULL OR s.shop_id=?)
                    AND (? IS NULL OR (substr(s.starts,1,10)<=? AND substr(s.ends,1,10)>=?))
                    ORDER BY s.starts DESC""", owner, uid, branch, branch, day, day, day)
        return [summarize(record, at) for record in records]

    match = re.fullmatch(r"/attendance/(\d+)/(check-in|check-out|requests)", path)
    if match and method == "POST":
        require(not owner, "Chỉ nhân viên thao tác trên ca cá nhân.", 403)
        aid, action = int(match[1]), match[2]
        row = one(db, ATTENDANCE + " WHERE a.id=? AND a.user_id=? AND s.published=1", aid, uid)
        require(row, "Không tìm thấy ca cá nhân.", 404)
        month = row["starts"][:7]
        mutable_month(db, month)
        if action == "check-in":
            if row["check_in"]:
                return summarize(row, at)
            require(row["starts"] <= at < row["ends"], "Chưa đến giờ hoặc đã hết ca check-in.", 409)
            db.execute("UPDATE attendance SET check_in=? WHERE id=?", (at, aid))
        elif action == "check-out":
            if row["check_out"]:
                return summarize(row, at)
            require(row["check_in"], "Cần check-in trước.", 409)
            require(row["starts"] <= at <= row["ends"] and row["check_in"] < at,
                    "Ngoài giờ ca. Hãy gửi giải trình bổ sung công.", 409)
            db.execute("UPDATE attendance SET check_out=? WHERE id=?", (at, aid))
        else:
            kind = data.get("kind")
            reason = string(data, "reason")
            require(kind in ("explanation", "correction"), "Loại yêu cầu không hợp lệ.")
            entry = exit_ = None
            if kind == "explanation":
                status = summarize(row, at)
                require(status["late"] or status["status"] == "absent",
                        "Chỉ giải trình ca đi muộn hoặc bỏ ca.", 409)
            else:
                require(at >= row["ends"], "Chỉ bổ sung công sau khi ca kết thúc.", 409)
                entry = parse_time(data.get("check_in"))
                exit_ = parse_time(data.get("check_out"))
                validate_correction(row, entry, exit_, at)
            rid = db.execute("""INSERT INTO requests(attendance_id,kind,reason,proposed_in,proposed_out,created)
                              VALUES (?,?,?,?,?,?)""", (aid, kind, reason, entry, exit_, at)).lastrowid
            for admin in rows(db, "SELECT id FROM users WHERE shop_id IS NULL"):
                notify(db, admin["id"], f"{row['name']} đã gửi yêu cầu cho ca {row['starts']}.", at)
            return {"id": rid, "status": "pending"}
        invalidate_confirmation(db, month, uid)
        return summarize(one(db, ATTENDANCE + " WHERE a.id=?", aid), at)

    if path == "/requests" and method == "GET":
        return rows(db, """SELECT r.*,a.user_id,a.check_in,a.check_out,s.starts,s.ends,s.shop_id,u.name
                           FROM requests r JOIN attendance a ON a.id=r.attendance_id
                           JOIN shifts s ON s.id=a.shift_id JOIN users u ON u.id=a.user_id
                           WHERE ? OR a.user_id=? ORDER BY r.id DESC""", owner, uid)

    match = re.fullmatch(r"/requests/(\d+)/review", path)
    if match and method == "POST":
        require(owner, "Chỉ chủ quán có quyền duyệt.", 403)
        request = one(db, "SELECT * FROM requests WHERE id=?", int(match[1]))
        require(request, "Không tìm thấy yêu cầu.", 404)
        require(request["status"] == "pending", "Yêu cầu đã được xử lý.", 409)
        row = one(db, ATTENDANCE + " WHERE a.id=?", request["attendance_id"])
        month = row["starts"][:7]
        mutable_month(db, month)
        approved = data.get("approve")
        require(type(approved) is bool, "Trường approve phải là true hoặc false.")
        reason = None if approved else string(data, "reason")
        if approved and request["kind"] == "correction":
            entry, exit_ = request["proposed_in"], request["proposed_out"]
            validate_correction(row, entry, exit_, at)
            # An approved absence does not excuse a newly established late arrival.
            excused = row["excused"] if row["check_in"] else 0
            db.execute("UPDATE attendance SET check_in=?,check_out=?,excused=? WHERE id=?",
                       (entry, exit_, excused, row["id"]))
        if approved and request["kind"] == "explanation":
            status = summarize(row, at)
            require(status["late"] or status["status"] == "absent",
                    "Ca đã thay đổi, hãy từ chối yêu cầu không còn phù hợp.", 409)
            db.execute("UPDATE attendance SET excused=1 WHERE id=?", (row["id"],))
        status = "approved" if approved else "rejected"
        db.execute("""UPDATE requests SET status=?,decision_reason=?,reviewed=?,
                      previous_in=?,previous_out=? WHERE id=?""",
                   (status, reason, at, row["check_in"], row["check_out"], request["id"]))
        if approved:
            invalidate_confirmation(db, month, row["user_id"])
        notify(db, row["user_id"], f"Yêu cầu #{request['id']} " +
               ("đã được duyệt." if approved else f"bị từ chối. Lý do: {reason}"), at)
        return {"status": status}

    if path == "/periods" and method == "GET":
        return rows(db, """SELECT p.*,t.confirmed FROM periods p LEFT JOIN statements t
                           ON t.month=p.month AND t.user_id=?
                           WHERE ? OR t.user_id IS NOT NULL ORDER BY p.month DESC""", uid, owner)
    match = re.fullmatch(rf"/periods/({MONTH})(?:/(confirm|close|export))?", path)
    if match:
        month, action = match[1], match[2]
        period = one(db, "SELECT * FROM periods WHERE month=?", month)
        require(period, "Kỳ công chưa mở.", 404)
        if not owner:
            require(action in (None, "confirm"), "Chỉ chủ quán có quyền chốt hoặc xuất.", 403)
            result = statement(db, month, uid, at)
            if action is None and method == "GET":
                return result
            if action == "confirm" and method == "POST":
                if result["confirmed"]:
                    return result
                mutable_month(db, month)
                require(not pending(db, month, uid), "Còn yêu cầu đang chờ duyệt.", 409)
                require(all(x["status"] in ("completed", "absent", "excused_absence") for x in result["entries"]),
                        "Còn ca thiếu giờ ra hoặc chưa kết thúc.", 409)
                db.execute("UPDATE statements SET confirmed=? WHERE month=? AND user_id=?", (at, month, uid))
                for admin in rows(db, "SELECT id FROM users WHERE shop_id IS NULL"):
                    notify(db, admin["id"], f"{actor['name']} đã xác nhận bảng công {month}.", at)
                return statement(db, month, uid, at)
        if owner and action is None and method == "GET":
            employees = rows(db, """SELECT t.user_id,u.name,u.shop_id,t.confirmed
                                    FROM statements t JOIN users u ON u.id=t.user_id
                                    WHERE t.month=? ORDER BY u.shop_id,u.name""", month)
            totals = []
            for branch in rows(db, "SELECT * FROM shops ORDER BY id"):
                staff = [item for item in employees if item["shop_id"] == branch["id"]]
                totals.append(dict(branch, total=len(staff), confirmed=sum(bool(x["confirmed"]) for x in staff)))
            confirmed = [statement(db, month, item["user_id"], at) for item in employees if item["confirmed"]]
            return dict(period, shops=totals, employees=employees, confirmed_statements=confirmed,
                        pending_requests=bool(pending(db, month)))
        if owner and action == "close" and method == "POST":
            if not period["closed"]:
                require(not pending(db, month), "Còn yêu cầu đang chờ duyệt.", 409)
                require(not one(db, "SELECT 1 FROM statements WHERE month=? AND confirmed IS NULL", month),
                        "Chưa đủ nhân viên xác nhận.", 409)
                db.execute("UPDATE periods SET closed=? WHERE month=?", (at, month))
            return {"ok": True}
        if owner and action == "export" and method == "GET":
            require(period["closed"], "Cần chốt kỳ công trước khi xuất Excel.", 409)
            return excel(db, month, at)
    raise APIError(404, "Không tìm thấy chức năng.")


def validate_correction(row, entry, exit_, at):
    require(entry < exit_ <= at and entry < row["ends"] and exit_ > row["starts"],
            "Giờ bổ sung phải hợp lệ và giao với khung giờ ca.")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in STATIC_ASSETS:
            filename, content_type = STATIC_ASSETS[path]
            self.send_payload(200, (FRONTEND / filename).read_bytes(), content_type)
            return
        self.handle_api()

    def handle_api(self):
        db = connect()
        try:
            data = {}
            if self.command == "POST":
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    require(0 <= size <= 32768, "Dữ liệu quá lớn.", 413)
                    data = json.loads(self.rfile.read(size)) if size else {}
                except (ValueError, UnicodeError):
                    raise APIError(400, "JSON không hợp lệ.") from None
                require(isinstance(data, dict), "JSON phải là một đối tượng.")
            target = urlsplit(self.path)
            db.execute("BEGIN IMMEDIATE" if self.command == "POST" else "BEGIN")
            result = dispatch(db, self.command, target.path, parse_qs(target.query), data,
                              self.headers.get("Authorization", ""), now())
            db.commit()
            if isinstance(result, bytes):
                self.send_payload(200, result, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                self.send_json(200, result)
        except APIError as error:
            db.rollback()
            self.send_json(error.status, {"error": error.message})
        except sqlite3.IntegrityError:
            db.rollback()
            self.send_json(409, {"error": "Dữ liệu đã tồn tại hoặc yêu cầu đang chờ xử lý."})
        except sqlite3.OperationalError as error:
            db.rollback()
            self.log_error("%s", error)
            self.send_json(503, {"error": "Cơ sở dữ liệu tạm thời không khả dụng."})
        finally:
            db.close()

    do_POST = handle_api

    def send_json(self, status, payload):
        self.send_payload(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def send_payload(self, status, payload, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        if content_type.endswith("spreadsheetml.sheet"):
            self.send_header("Content-Disposition", 'attachment; filename="bang-cong.xlsx"')
        self.end_headers()
        self.wfile.write(payload)


def main():
    from threading import Thread

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", default=8000, type=int)
    account = commands.add_parser("add-user")
    account.add_argument("username")
    account.add_argument("name")
    account.add_argument("--shop", choices=(1, 2), type=int)
    account.add_argument("--hourly-rate", default=0, type=int)
    args = parser.parse_args()
    initialize(DB)
    with connect() as db:
        if args.command == "add-user":
            password = getpass("Mật khẩu: ")
            if not 8 <= len(password) <= 256 or args.hourly_rate < 0:
                parser.error("Mật khẩu cần 8–256 ký tự và đơn giá không được âm.")
            salt = secrets.token_hex(16)
            db.execute("INSERT INTO users(username,name,password,shop_id,hourly_rate) VALUES (?,?,?,?,?)",
                       (args.username, args.name, f"{salt}:{password_hash(password, salt)}",
                        args.shop, args.hourly_rate))
            if args.shop is None:
                db.execute("""UPDATE employee_metadata SET joined_on=?
                              WHERE user_id=(SELECT id FROM users WHERE username=?)""",
                           (now()[:10],args.username))
            if args.shop is not None:
                for admin in rows(db, """SELECT u.id FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                        WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active')"""):
                    notify(db, admin["id"], f"Nhân viên {args.name} vừa được tạo và đang chờ duyệt.", now())
                print("Tài khoản nhân viên đang chờ chủ quán duyệt.")
            return
        db.execute("BEGIN IMMEDIATE")
        open_periods(db, now())
    Thread(target=notify_loop, daemon=True).start()
    print(f"Timezy API: http://{args.host}:{args.port}", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
