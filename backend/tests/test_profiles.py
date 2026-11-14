import base64
import hashlib
from io import BytesIO
import sqlite3
import unittest

from PIL import Image

from backend import app


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(app.SCHEMA.read_text(encoding="utf-8"))
        self.addCleanup(self.db.close)
        for uid,shop in ((1,None),(2,1),(3,2)):
            self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,25000)",
                            (uid,f"user{uid}",f"Person {uid}","not-exposed",shop))
            self.db.execute("INSERT INTO sessions VALUES (?,?,?)",
                            (hashlib.sha256(f"token{uid}".encode()).hexdigest(),uid,"2027-01-01T00:00:00+07:00"))
        self.db.execute("UPDATE account_profiles SET status='active'")
        self.db.commit()
        self.values=dict(name="Nguyen Minh Anh",birth_date="2000-01-15",gender="female",
                         email="minhanh@example.com",phone="0901234567",national_id="012345678901")

    def call(self,path,user=2,method="POST",**data):
        with self.db:
            return app.dispatch(self.db,method,path,{},data,f"Bearer token{user}","2026-11-14T10:00:00+07:00")

    def test_details_saved_and_private_employment_fields_readonly(self):
        before=self.call("/me",method="GET")
        self.assertEqual(before["employee_code"],"NV000002")
        self.assertEqual(before["shop_name"],"Đảo Matcha")
        self.assertIsNone(before["joined_on"])
        result=self.call("/me/profile",**self.values)
        self.assertEqual(result["email"],self.values["email"])
        self.assertEqual(result["phone"],"+84901234567")
        self.assertEqual(result["national_id"],self.values["national_id"])
        self.assertEqual(result["hourly_rate"],25000)
        self.assertEqual(self.call("/me",method="GET")["name"],self.values["name"])
        self.assertIsNone(self.call("/me",user=3,method="GET")["national_id"])
        self.assertNotIn("password",result)
        self.assertNotIn("token",result)
        for key,value in (("user_id",3),("hourly_rate",999999),("employee_code","NV-FAKE"),
                          ("joined_on","1990-01-01"),("shop_id",2)):
            with self.subTest(key=key):
                with self.assertRaises(app.APIError) as error:
                    self.call("/me/profile",**dict(self.values,**{key:value}))
                self.assertEqual(error.exception.status,403)

    def test_invalid_and_duplicate_details_do_not_partially_update(self):
        self.call("/me/profile",**self.values)
        with self.assertRaises(app.APIError):
            self.call("/me/profile",name="Changed",**{k:v for k,v in self.values.items() if k!="name"},
                      hourly_rate=100)
        with self.assertRaises(app.APIError):
            self.call("/me/profile",**dict(self.values,national_id="123"))
        with self.assertRaises(app.APIError):
            self.call("/me/profile",user=3,**dict(self.values,name="Other",national_id="999999999999"))
        self.assertEqual(self.call("/me",method="GET")["name"],self.values["name"])
        self.assertEqual(self.call("/me",user=3,method="GET")["name"],"Person 3")

    def test_avatar_persists_and_rejects_invalid_images(self):
        stream=BytesIO()
        Image.new("RGB",(128,128),(80,120,90)).save(stream,format="JPEG")
        avatar="data:image/jpeg;base64,"+base64.b64encode(stream.getvalue()).decode("ascii")
        self.call("/me/avatar",avatar=avatar)
        result=self.call("/me",method="GET")
        self.assertTrue(result["avatar"].startswith("data:image/jpeg;base64,"))
        with Image.open(BytesIO(base64.b64decode(result["avatar"].split(",")[1]))) as image:
            self.assertEqual(image.size,(128,128))
        for invalid in ("https://example.com/photo.jpg","data:image/svg+xml;base64,PHN2Zz4=",
                        "data:image/jpeg;base64,/9j/AAAA/9k="):
            with self.subTest(invalid=invalid):
                with self.assertRaises(app.APIError):
                    self.call("/me/avatar",avatar=invalid)
        self.call("/me/avatar",avatar=None)
        self.assertIsNone(self.call("/me",method="GET")["avatar"])


if __name__=="__main__":
    unittest.main()
