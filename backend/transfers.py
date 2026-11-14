import re


class TransferError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def require(condition, message, status=400):
    if not condition:
        raise TransferError(message, status)


def records(db, sql, *args):
    return [dict(row) for row in db.execute(sql, args)]


def assignment(db, aid):
    return db.execute("""SELECT a.*,s.shop_id,s.starts,s.ends,s.published,
                          EXISTS(SELECT 1 FROM periods p WHERE p.month=substr(s.starts,1,7)
                                 AND p.closed IS NOT NULL) AS closed
                          FROM attendance a JOIN shifts s ON s.id=a.shift_id WHERE a.id=?""",
                      (aid,)).fetchone()


def transferable(db, item, at):
    require(item and item["published"], "Không tìm thấy ca đã xếp.",404)
    require(not item["closed"] and item["starts"]>at and not item["check_in"] and not item["check_out"],
            "Chỉ đổi ca chưa bắt đầu và chưa chấm công.",409)
    require(not db.execute("SELECT 1 FROM requests WHERE attendance_id=?", (item["id"],)).fetchone(),
            "Ca đã có yêu cầu điều chỉnh công.",409)


def candidates(db, item, sender):
    return records(db, """SELECT u.id,u.name FROM users u
                     LEFT JOIN account_profiles p ON p.user_id=u.id
                     WHERE u.shop_id=? AND u.id<>? AND (p.status IS NULL OR p.status='active')
                     AND NOT EXISTS (SELECT 1 FROM attendance a JOIN shifts s ON s.id=a.shift_id
                         WHERE a.user_id=u.id AND s.published=1 AND s.starts<? AND s.ends>?)
                     ORDER BY u.name""",item["shop_id"],sender,item["ends"],item["starts"])


def notify(db, uid, message, at):
    db.execute("INSERT INTO notifications(user_id,message,created) VALUES (?,?,?)",(uid,message,at))


def handle_transfers(db, method, path, data, actor, at):
    uid = actor["id"]
    if path=="/shift-transfers" and method=="GET":
        return records(db, """SELECT t.*,s.starts,s.ends,s.shop_id,
                    sender.name AS sender_name,receiver.name AS recipient_name,
                    CASE WHEN t.status='pending' AND
                      (s.starts<=? OR a.id IS NULL OR a.user_id<>t.sender_id OR a.check_in IS NOT NULL
                       OR s.published=0)
                      THEN 'expired' ELSE t.status END AS display_status
                    FROM shift_transfers t JOIN shifts s ON s.id=t.shift_id
                    JOIN users sender ON sender.id=t.sender_id JOIN users receiver ON receiver.id=t.recipient_id
                    LEFT JOIN attendance a ON a.id=t.attendance_id
                    WHERE ? OR t.sender_id=? OR t.recipient_id=?
                    ORDER BY t.id DESC""",at,actor["shop_id"] is None,uid,uid)

    match=re.fullmatch(r"/attendance/(\d+)/(replacements|transfer)",path)
    if match:
        require(actor["shop_id"] is not None,"Chỉ nhân viên gửi yêu cầu đổi ca.",403)
        aid,action=int(match[1]),match[2]
        item=assignment(db,aid)
        require(item and item["user_id"]==uid,"Không tìm thấy ca cá nhân.",404)
        transferable(db,item,at)
        if method=="GET" and action=="replacements":
            return candidates(db,item,uid)
        if method=="POST" and action=="transfer":
            target=data.get("recipient_id")
            require(type(target) is int,"Chọn nhân viên thay ca.")
            require(target in {c["id"] for c in candidates(db,item,uid)},
                    "Người thay phải cùng quán, đã được duyệt và không có ca trùng giờ.",409)
            require(not db.execute("SELECT 1 FROM shift_transfers WHERE attendance_id=? AND status='pending'",
                                   (aid,)).fetchone(),"Ca đang có yêu cầu đổi chờ xác nhận.",409)
            tid=db.execute("""INSERT INTO shift_transfers(attendance_id,shift_id,sender_id,recipient_id,created)
                              VALUES (?,?,?,?,?)""",(aid,item["shift_id"],uid,target,at)).lastrowid
            notify(db,target,f"{actor['name']} nhờ bạn thay ca {item['starts']} đến {item['ends']}. Mở Ca làm của tôi để xác nhận.",at)
            return {"id":tid,"status":"pending"}

    match=re.fullmatch(r"/shift-transfers/(\d+)/(respond|cancel)",path)
    if match and method=="POST":
        tid,action=int(match[1]),match[2]
        transfer=db.execute("SELECT * FROM shift_transfers WHERE id=?", (tid,)).fetchone()
        require(transfer,"Không tìm thấy yêu cầu đổi ca.",404)
        if action=="cancel":
            require(uid==transfer["sender_id"],"Chỉ người gửi được hủy yêu cầu.",403)
            if transfer["status"]=="cancelled":
                return {"status":"cancelled"}
            require(transfer["status"]=="pending","Yêu cầu đã được xử lý.",409)
            db.execute("UPDATE shift_transfers SET status='cancelled',responded=? WHERE id=?",(at,tid))
            notify(db,transfer["recipient_id"],f"Yêu cầu đổi ca #{tid} đã được người gửi hủy.",at)
            return {"status":"cancelled"}
        require(uid==transfer["recipient_id"],"Chỉ người được nhờ thay ca được trả lời.",403)
        accept=data.get("accept")
        require(type(accept) is bool,"Trường accept phải là true hoặc false.")
        status="accepted" if accept else "rejected"
        if transfer["status"]==status:
            return {"status":status}
        require(transfer["status"]=="pending","Yêu cầu đã được xử lý.",409)
        item=assignment(db,transfer["attendance_id"])
        transferable(db,item,at)
        require(item["user_id"]==transfer["sender_id"],"Ca đã được chuyển cho người khác.",409)
        if accept:
            require(uid in {c["id"] for c in candidates(db,item,transfer["sender_id"])},
                    "Bạn không thể nhận ca do trùng lịch hoặc thay đổi cơ sở.",409)
            rate=db.execute("SELECT hourly_rate FROM users WHERE id=?", (uid,)).fetchone()["hourly_rate"]
            db.execute("UPDATE attendance SET user_id=?,hourly_rate=? WHERE id=?",(uid,rate,item["id"]))
            db.execute("DELETE FROM registrations WHERE shift_id=? AND user_id=?",
                       (item["shift_id"],transfer["sender_id"]))
            db.execute("INSERT OR IGNORE INTO registrations VALUES (?,?)",(item["shift_id"],uid))
            # Invalidate an old confirmed statement if legacy data opened this period early.
            db.execute("UPDATE statements SET confirmed=NULL WHERE month=? AND user_id IN (?,?)",
                       (item["starts"][:7],uid,transfer["sender_id"]))
            db.execute("""UPDATE shift_transfers SET status='cancelled',responded=?
                          WHERE attendance_id=? AND status='pending' AND id<>?""",(at,item["id"],tid))
        db.execute("UPDATE shift_transfers SET status=?,responded=? WHERE id=?",(status,at,tid))
        message=(f"{actor['name']} đã đồng ý nhận ca {item['starts']}." if accept
                 else f"{actor['name']} đã từ chối yêu cầu thay ca {item['starts']}.")
        notify(db,transfer["sender_id"],message,at)
        notify(db,uid,("Đã nhận ca. Lịch làm của bạn đã cập nhật." if accept else "Đã từ chối yêu cầu thay ca."),at)
        if accept:
            for owner in records(db,"""SELECT u.id FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id
                                       WHERE u.shop_id IS NULL AND (p.status IS NULL OR p.status='active')"""):
                notify(db,owner["id"],f"Ca {item['starts']} đã chuyển từ nhân viên #{transfer['sender_id']} sang {actor['name']}.",at)
        return {"status":status}
    raise TransferError("Không tìm thấy chức năng.",404)
