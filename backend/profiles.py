import base64
import binascii
import re
from datetime import date
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


class ProfileError(Exception):
    def __init__(self, message, status=400):
        self.message,self.status=message,status


def require(condition,message,status=400):
    if not condition:
        raise ProfileError(message,status)


def text(data,key,maximum):
    value=data.get(key)
    require(isinstance(value,str) and 0<len(value.strip())<=maximum,f"Trường {key} không hợp lệ.")
    return value.strip()


def profile_info(db,uid):
    row=db.execute("""SELECT u.id,u.name,u.username,u.shop_id,u.hourly_rate,
                      s.name AS shop_name,d.birth_date,d.gender,d.email,d.phone,
                      m.employee_code,m.national_id,m.joined_on,m.avatar,m.language
                      FROM users u LEFT JOIN shops s ON s.id=u.shop_id
                      LEFT JOIN account_details d ON d.user_id=u.id
                      LEFT JOIN employee_metadata m ON m.user_id=u.id WHERE u.id=?""",(uid,)).fetchone()
    result=dict(row)
    result["role"]="owner" if row["shop_id"] is None else "employee"
    result["language"]=result["language"] or "vi"
    return result


def update_profile(db,uid,data,at):
    require(not set(data).intersection({"user_id","hourly_rate","employee_code","joined_on","shop_id","role"}),
            "Không thể tự thay đổi thông tin công việc.",403)
    name=text(data,"name",100)
    birth=text(data,"birth_date",10)
    try:
        born=date.fromisoformat(birth)
        require(born.isoformat()==birth and born<date.fromisoformat(at[:10]),"Ngày sinh không hợp lệ.")
    except ValueError:
        raise ProfileError("Ngày sinh không hợp lệ.") from None
    gender=data.get("gender")
    require(gender in ("male","female","other"),"Hãy chọn giới tính.")
    email=text(data,"email",254).lower()
    require(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email),"Email không hợp lệ.")
    phone=re.sub(r"[\s().-]","",text(data,"phone",30))
    if phone.startswith("0"):
        phone="+84"+phone[1:]
    require(re.fullmatch(r"\+?[1-9][0-9]{8,14}",phone),"Số điện thoại không hợp lệ.")
    national_id=data.get("national_id","")
    require(isinstance(national_id,str),"CCCD không hợp lệ.")
    national_id=national_id.strip() or None
    require(national_id is None or re.fullmatch(r"[0-9]{12}",national_id),"CCCD cần đủ 12 chữ số.")
    require(not db.execute("SELECT 1 FROM account_details WHERE user_id<>? AND (email=? OR phone=?)",
                           (uid,email,phone)).fetchone(),"Email hoặc số điện thoại đã được sử dụng.",409)
    if national_id:
        require(not db.execute("SELECT 1 FROM employee_metadata WHERE user_id<>? AND national_id=?",
                               (uid,national_id)).fetchone(),"CCCD đã được sử dụng.",409)
    db.execute("UPDATE users SET name=? WHERE id=?",(name,uid))
    db.execute("""INSERT INTO account_details VALUES (?,?,?,?,?)
                  ON CONFLICT(user_id) DO UPDATE SET birth_date=excluded.birth_date,
                  gender=excluded.gender,email=excluded.email,phone=excluded.phone""",
               (uid,birth,gender,email,phone))
    db.execute("UPDATE employee_metadata SET national_id=? WHERE user_id=?",(national_id,uid))
    return profile_info(db,uid)


def update_avatar(db,uid,data):
    avatar=data.get("avatar")
    if avatar is not None:
        require(isinstance(avatar,str) and len(avatar)<=24000,"Ảnh đại diện vượt dung lượng cho phép.")
        require(avatar.startswith("data:image/jpeg;base64,"),"Ảnh đại diện phải là JPEG.")
        try:
            decoded=base64.b64decode(avatar.split(",",1)[1],validate=True)
        except (ValueError,binascii.Error):
            raise ProfileError("Ảnh đại diện không hợp lệ.") from None
        require(decoded.startswith(b"\xff\xd8\xff") and decoded.endswith(b"\xff\xd9"),"Ảnh JPEG không hợp lệ.")
        try:
            with Image.open(BytesIO(decoded)) as image:
                require(image.format=="JPEG" and max(image.size)<=512,"Ảnh đại diện không hợp lệ.")
                normalized=ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"),(128,128))
                output=BytesIO()
                normalized.save(output,format="JPEG",quality=85)
                avatar="data:image/jpeg;base64,"+base64.b64encode(output.getvalue()).decode("ascii")
        except (UnidentifiedImageError,OSError,ValueError,SyntaxError,Image.DecompressionBombError):
            raise ProfileError("Không đọc được ảnh đại diện.") from None
    db.execute("UPDATE employee_metadata SET avatar=? WHERE user_id=?",(avatar,uid))
    return profile_info(db,uid)
