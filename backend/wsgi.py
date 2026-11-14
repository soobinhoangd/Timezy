"""Production HTTP adapter using the same API dispatch as the local server."""

from http import HTTPStatus
import json
import logging
import sqlite3
from urllib.parse import parse_qs

from backend import app


def application(environ,start_response):
    method=environ.get("REQUEST_METHOD","GET")
    path=environ.get("PATH_INFO","/")
    status=200
    content_type="application/json; charset=utf-8"
    db=None
    attachment=False
    try:
        if method in ("GET","HEAD") and path in app.STATIC_ASSETS:
            filename,content_type=app.STATIC_ASSETS[path]
            payload=(app.FRONTEND/filename).read_bytes()
        else:
            app.require(method in ("GET","POST","HEAD"),"Phương thức không được hỗ trợ.",405)
            data={}
            if method=="POST":
                try:
                    size=int(environ.get("CONTENT_LENGTH") or "0")
                    app.require(0<=size<=32768,"Dữ liệu quá lớn.",413)
                    data=json.loads(environ["wsgi.input"].read(size)) if size else {}
                except (ValueError,UnicodeError):
                    raise app.APIError(400,"JSON không hợp lệ.") from None
                app.require(isinstance(data,dict),"JSON phải là một đối tượng.")
            db=app.connect()
            db.execute("BEGIN IMMEDIATE" if method=="POST" else "BEGIN")
            result=app.dispatch(db,"GET" if method=="HEAD" else method,path,
                                parse_qs(environ.get("QUERY_STRING","")),data,
                                environ.get("HTTP_AUTHORIZATION",""),app.now())
            db.commit()
            if isinstance(result,bytes):
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                attachment=True
                payload=result
            else:
                payload=json.dumps(result,ensure_ascii=False).encode()
    except app.APIError as error:
        status=error.status
        payload=json.dumps({"error":error.message},ensure_ascii=False).encode()
    except sqlite3.IntegrityError:
        status=409
        payload=json.dumps({"error":"Dữ liệu đã tồn tại hoặc yêu cầu đang chờ xử lý."},ensure_ascii=False).encode()
    except sqlite3.OperationalError:
        logging.exception("Database temporarily unavailable")
        status=503
        payload=json.dumps({"error":"Cơ sở dữ liệu tạm thời không khả dụng."},ensure_ascii=False).encode()
    except Exception:
        logging.exception("Request failed")
        status=500
        content_type="application/json; charset=utf-8"
        payload=b'{"error":"Internal server error"}'
    finally:
        if db is not None:
            db.rollback()
            db.close()
    headers=[("Content-Type",content_type),("Content-Length",str(len(payload))),
             ("Cache-Control","no-store"),("X-Content-Type-Options","nosniff")]
    if attachment:
        headers.append(("Content-Disposition",'attachment; filename="bang-cong.xlsx"'))
    start_response(f"{status} {HTTPStatus(status).phrase}",headers)
    return [b"" if method=="HEAD" else payload]
