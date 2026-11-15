from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import app
from backend.deploy import bootstrap_owner
from backend.wsgi import application


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(temporary.cleanup)
        self.db_path=str(Path(temporary.name)/"persistent.sqlite3")
        patched=patch.object(app,"DB",self.db_path)
        patched.start()
        self.addCleanup(patched.stop)

    def bootstrap(self):
        with patch.dict(os.environ,{"TIMEZY_ADMIN_USERNAME":"owner","TIMEZY_ADMIN_PASSWORD":"Secure-test-password-123"}):
            bootstrap_owner()

    def request(self,path,method="GET",data=None,token="",raw=None,length=None):
        body=json.dumps(data).encode() if data is not None else raw or b""
        environ={"REQUEST_METHOD":method,"PATH_INFO":path,"QUERY_STRING":"",
                 "CONTENT_LENGTH":str(len(body) if length is None else length),
                 "wsgi.input":BytesIO(body),"HTTP_AUTHORIZATION":"Bearer "+token}
        response={}
        def started(status,headers):
            response.update(status=int(status.split()[0]),headers=dict(headers))
        response["body"]=b"".join(application(environ,started))
        return response

    def test_first_owner_required_and_not_reset_on_restart(self):
        with patch.dict(os.environ):
            os.environ.pop("TIMEZY_ADMIN_USERNAME",None)
            os.environ.pop("TIMEZY_ADMIN_PASSWORD",None)
            with self.assertRaises(RuntimeError):
                bootstrap_owner()
        self.bootstrap()
        with patch.dict(os.environ,{"TIMEZY_ADMIN_USERNAME":"other","TIMEZY_ADMIN_PASSWORD":"Different-password-123"}):
            bootstrap_owner()
        db=app.connect()
        try:
            accounts=db.execute("SELECT * FROM users").fetchall()
            self.assertEqual(len(accounts),1)
            self.assertEqual(accounts[0]["username"],"owner")
            self.assertTrue(app.matches_password(accounts[0],"Secure-test-password-123"))
            self.assertFalse(app.matches_password(accounts[0],"Different-password-123"))
        finally:
            db.close()

    def test_production_static_login_permissions_and_bad_requests(self):
        self.bootstrap()
        self.assertEqual(self.request("/health")["status"],200)
        for path in ("/","/app.js","/styles.css","/attendance-state.js"):
            response=self.request(path)
            self.assertEqual(response["status"],200)
            self.assertGreater(len(response["body"]),100)
        self.assertEqual(self.request("/me")["status"],401)
        login=self.request("/login","POST",{"username":"owner","password":"Secure-test-password-123"})
        self.assertEqual(login["status"],200)
        token=json.loads(login["body"])["token"]
        profile=self.request("/me",token=token)
        self.assertEqual(json.loads(profile["body"])["role"],"owner")
        self.assertEqual(self.request("/../database/schema.sql",token=token)["status"],404)
        self.assertEqual(self.request("/login","POST",raw=b"{")["status"],400)
        self.assertEqual(self.request("/login","POST",raw=b"[]")["status"],400)
        self.assertEqual(self.request("/login","POST",length=32769)["status"],413)
        head=self.request("/health",method="HEAD")
        self.assertEqual(head["status"],200)
        self.assertEqual(head["body"],b"")
        self.request("/logout","POST",{},token=token)
        self.assertEqual(self.request("/me",token=token)["status"],401)

    def test_prefixed_api_preserves_auth_and_session_revocation(self):
        self.bootstrap()
        self.assertEqual(self.request("/api/health")["status"],200)
        self.assertEqual(self.request("/api/me")["status"],401)
        login=self.request("/api/login","POST",{"username":"owner","password":"Secure-test-password-123"})
        self.assertEqual(login["status"],200)
        token=json.loads(login["body"])["token"]
        profile=self.request("/api/me",token=token)
        self.assertEqual(json.loads(profile["body"])["role"],"owner")
        self.assertEqual(profile["headers"]["Cache-Control"],"no-store")
        self.assertEqual(self.request("/api/logout","POST",{},token=token)["status"],200)
        self.assertEqual(self.request("/api/me",token=token)["status"],401)


if __name__=="__main__":
    unittest.main()
