from datetime import date, datetime, timedelta
import re

SLOTS = (("morning", "Ca sáng"), ("afternoon", "Ca chiều"),
         ("evening", "Tối full"), ("split", "Tối gãy"))


class WeeklyError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def require(condition, message, status=400):
    if not condition:
        raise WeeklyError(message, status)


def records(db, sql, *args):
    return [dict(row) for row in db.execute(sql, args)]


def bounds(at):
    today = date.fromisoformat(at[:10])
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=7)


def handle_weekly(db, method, path, query, data, actor, at, publish):
    owner = actor["shop_id"] is None
    branch = query.get("shop_id", [None])[0] if method == "GET" else data.get("shop_id")
    if not owner:
        require(branch is None or str(branch) == str(actor["shop_id"]), "Sai cơ sở.", 403)
        branch = actor["shop_id"]
    require(str(branch) in ("1", "2"), "Hãy chọn cơ sở.")
    branch = int(branch)
    monday, next_monday = bounds(at)
    next_days = [(next_monday+timedelta(days=i)).isoformat() for i in range(7)]
    templates = records(db, "SELECT * FROM shift_templates WHERE shop_id=?", branch)

    if method == "GET" and path == "/weekly":
        week = query.get("week", ["current"])[0]
        require(week in ("current", "next"), "Tuần không hợp lệ.")
        start = monday if week == "current" else next_monday
        end = start + timedelta(days=7)
        days = [(start + timedelta(days=i)).isoformat() for i in range(7)]
        staff = records(db, """SELECT u.id,u.name FROM users u
                    LEFT JOIN account_profiles p ON p.user_id=u.id
                    WHERE u.shop_id=? AND (p.status IS NULL OR p.status='active')
                    ORDER BY u.name""", branch)
        schedule = records(db, """SELECT a.user_id,s.id,s.starts,s.ends FROM attendance a
                    JOIN shifts s ON s.id=a.shift_id WHERE s.shop_id=? AND s.published=1
                    AND s.starts<? AND s.ends>? ORDER BY s.starts""",
                    branch, end.isoformat()+"T00:00:00+07:00", start.isoformat()+"T00:00:00+07:00")
        available = records(db, """SELECT w.*,u.name FROM weekly_availability w
                    JOIN users u ON u.id=w.user_id LEFT JOIN account_profiles p ON p.user_id=u.id
                    JOIN weekly_submissions submitted ON submitted.user_id=w.user_id
                      AND submitted.week_start=date(w.day,'weekday 0','-6 days')
                    WHERE u.shop_id=? AND w.day>=? AND w.day<?
                    AND (p.status IS NULL OR p.status='active')""", branch, start.isoformat(), end.isoformat())
        mapped = records(db, """SELECT w.*,s.published FROM weekly_slots w
                    JOIN shifts s ON s.id=w.shift_id WHERE w.shop_id=? AND w.day>=? AND w.day<?""",
                    branch, start.isoformat(), end.isoformat())
        cells = []
        for day in days:
            for slot, label in SLOTS:
                mapping = next((m for m in mapped if m["day"] == day and m["slot"] == slot), None)
                candidates = [a for a in available if a["day"] == day and a["slot"] == slot]
                cells.append({"day": day, "slot": slot, "published": bool(mapping and mapping["published"]),
                              "shift_id": mapping["shift_id"] if mapping else None,
                              "registered": any(a["user_id"] == actor["id"] for a in candidates),
                              "candidates": [{"id":a["user_id"],"name":a["name"]} for a in candidates] if owner else []})
        submission = db.execute("SELECT * FROM weekly_submissions WHERE user_id=? AND week_start=?",
                                (actor["id"],start.isoformat())).fetchone()
        return {"shop_id": branch, "week": week, "days": days, "templates": templates,
                "employees": staff, "schedule": schedule, "cells": cells,
                "submission":dict(submission) if submission else None}

    if path == "/weekly/availability" and method == "POST":
        raise WeeklyError("Hãy tải lại trang và bấm Xác nhận đăng ký để gửi lịch tuần.",409)

    if path == "/weekly/confirm" and method == "POST":
        require(not owner, "Chỉ nhân viên đăng ký lịch.", 403)
        require(data.get("week_start")==next_monday.isoformat(), "Chỉ xác nhận lịch tuần sau.")
        chosen, revision = data.get("slots"), data.get("revision")
        require(isinstance(chosen,list) and len(chosen)<=28, "Danh sách ca không hợp lệ.")
        require(type(revision) is int and revision>=0, "Phiên bản đăng ký không hợp lệ.")
        desired=set()
        for item in chosen:
            require(isinstance(item,dict), "Ca đăng ký không hợp lệ.")
            day,slot=item.get("day"),item.get("slot")
            require(isinstance(day,str) and day in next_days and isinstance(slot,str) and slot in dict(SLOTS),
                    "Ca đăng ký phải thuộc tuần sau.")
            desired.add((day,slot))
        existing=records(db,"SELECT day,slot FROM weekly_availability WHERE user_id=? AND day>=? AND day<?",
                         actor["id"],next_days[0],(next_monday+timedelta(days=7)).isoformat())
        previous={(item["day"],item["slot"]) for item in existing}
        submitted=db.execute("SELECT revision FROM weekly_submissions WHERE user_id=? AND week_start=?",
                             (actor["id"],next_days[0])).fetchone()
        require(revision==(submitted["revision"] if submitted else 0),
                "Đăng ký đã thay đổi ở tab khác. Hãy tải lại trước khi chỉnh sửa.",409)
        locked=records(db,"""SELECT w.day,w.slot FROM weekly_slots w JOIN shifts s ON s.id=w.shift_id
                            WHERE w.shop_id=? AND w.day>=? AND w.day<? AND s.published=1""",
                       branch,next_days[0],(next_monday+timedelta(days=7)).isoformat())
        require(all(((item["day"],item["slot"]) in previous)==((item["day"],item["slot"]) in desired)
                    for item in locked), "Ca đã công bố và không thể chỉnh sửa.",409)
        db.execute("DELETE FROM weekly_availability WHERE user_id=? AND day>=? AND day<?",
                   (actor["id"],next_days[0],(next_monday+timedelta(days=7)).isoformat()))
        db.executemany("INSERT INTO weekly_availability VALUES (?,?,?)",
                       [(actor["id"],day,slot) for day,slot in sorted(desired)])
        db.execute("""INSERT INTO weekly_submissions VALUES (?,?,?,?)
                      ON CONFLICT(user_id,week_start) DO UPDATE
                      SET revision=excluded.revision,confirmed_at=excluded.confirmed_at""",
                   (actor["id"],next_days[0],revision+1,at))
        for admin in records(db,"""SELECT u.id FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                   WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active')"""):
            db.execute("INSERT INTO notifications(user_id,message,created) VALUES (?,?,?)",
                       (admin["id"],f"{actor['name']} đã xác nhận đăng ký tuần {next_days[0]}.",at))
        return {"ok":True,"revision":revision+1}

    require(owner, "Chỉ chủ quán có quyền cấu hình và xếp lịch.", 403)
    if path == "/weekly/settings" and method == "POST":
        values = data.get("templates")
        require(isinstance(values,list) and len(values)==4, "Cần đủ bốn ca.")
        require(all(isinstance(item,dict) for item in values), "Cấu hình ca không hợp lệ.")
        require({item.get("slot") for item in values} == set(dict(SLOTS)), "Cần đủ bốn ca khác nhau.")
        for item in values:
            begin, finish = item.get("starts"), item.get("ends")
            require(all(isinstance(t,str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",t)
                        for t in (begin,finish)), "Giờ ca phải có dạng HH:MM.")
            require(begin!=finish, "Giờ bắt đầu và kết thúc cần khác nhau.")
            if item["slot"] in ("evening","split"):
                require(begin==("18:00" if item["slot"]=="evening" else "20:00"),
                        "Ca tối full bắt đầu 18h, ca tối gãy bắt đầu 20h.")
            db.execute("UPDATE shift_templates SET starts=?,ends=? WHERE shop_id=? AND slot=?",
                       (begin,finish,branch,item["slot"]))
        return {"ok": True}

    if path == "/weekly/publish" and method == "POST":
        day, slot, selected = data.get("day"), data.get("slot"), data.get("employee_ids")
        require(isinstance(day,str) and day in next_days,
                "Chỉ xếp lịch tuần sau.")
        require(isinstance(slot,str) and slot in dict(SLOTS), "Ca không hợp lệ.")
        require(isinstance(selected,list) and selected and all(type(i) is int and i>0 for i in selected),
                "Chọn ít nhất một nhân viên.")
        template = next(t for t in templates if t["slot"]==slot)
        require(template["starts"] and template["ends"], "Chủ quán cần cấu hình giờ ca trước khi công bố.")
        candidates = records(db, """SELECT w.user_id FROM weekly_availability w JOIN users u ON u.id=w.user_id
                    LEFT JOIN account_profiles p ON p.user_id=u.id
                    JOIN weekly_submissions submitted ON submitted.user_id=w.user_id
                      AND submitted.week_start=date(w.day,'weekday 0','-6 days')
                    WHERE w.day=? AND w.slot=? AND u.shop_id=?
                    AND (p.status IS NULL OR p.status='active')""", day,slot,branch)
        require(set(selected).issubset({c["user_id"] for c in candidates}),
                "Chỉ chọn người đã đăng ký đúng ca tại quán này.")
        mapping = db.execute("SELECT shift_id FROM weekly_slots WHERE shop_id=? AND day=? AND slot=?",
                             (branch,day,slot)).fetchone()
        if mapping:
            sid = mapping["shift_id"]
        else:
            start = datetime.fromisoformat(day+"T"+template["starts"]+":00+07:00")
            end = datetime.fromisoformat(day+"T"+template["ends"]+":00+07:00")
            if end<=start:
                end+=timedelta(days=1)
            db.execute("INSERT OR IGNORE INTO shifts(shop_id,starts,ends) VALUES (?,?,?)",
                       (branch,start.isoformat(),end.isoformat()))
            sid = db.execute("SELECT id FROM shifts WHERE shop_id=? AND starts=? AND ends=?",
                             (branch,start.isoformat(),end.isoformat())).fetchone()["id"]
            db.execute("INSERT INTO weekly_slots VALUES (?,?,?,?)", (branch,day,slot,sid))
        for candidate in candidates:
            db.execute("INSERT OR IGNORE INTO registrations VALUES (?,?)", (sid,candidate["user_id"]))
        return publish(sid,selected)
    raise WeeklyError("Không tìm thấy chức năng.",404)
