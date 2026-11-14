def shift_slot(db, shift):
    mapped = db.execute("SELECT slot FROM weekly_slots WHERE shift_id=?", (shift["id"],)).fetchone()
    if mapped:
        return mapped["slot"]
    clock = shift["starts"][11:16]
    template = db.execute("SELECT slot FROM shift_templates WHERE shop_id=? AND starts=?",
                          (shift["shop_id"],clock)).fetchone()
    if template:
        return template["slot"]
    if clock >= "20:00":
        return "split"
    if clock >= "18:00":
        return "evening"
    return "afternoon" if clock >= "12:00" else "morning"


def position_occupied(db, shift):
    others = db.execute("""SELECT DISTINCT s.* FROM shifts s JOIN attendance a ON a.shift_id=s.id
                           WHERE s.shop_id=? AND substr(s.starts,1,10)=? AND s.id<>?""",
                        (shift["shop_id"],shift["starts"][:10],shift["id"])).fetchall()
    slot = shift_slot(db,shift)
    return any(shift_slot(db,other)==slot for other in others)
