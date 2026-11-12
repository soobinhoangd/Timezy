# Timezy

Backend và frontend web cho ứng dụng chấm công Đảo Matcha và Mixue. Mỗi nhân viên thuộc một cơ sở. Chủ quán quản lý cả hai cơ sở.

## Cấu trúc dự án

```text
backend/
  app.py                API, phân quyền và tác vụ nghiệp vụ
  requirements.txt      Thư viện Python
  tests/                Kiểm thử luồng và lưu trữ
frontend/
  index.html            Khung giao diện
  styles.css            Giao diện desktop và điện thoại
  app.js                Màn hình và kết nối API
database/
  schema.sql            Bảng và chỉ mục
  connection.py         Kết nối và khởi tạo SQLite
  data/                 File dữ liệu thực tế
```

## Chạy local

Để thử ngay với dữ liệu mẫu, chạy `python -m backend.demo` rồi mở http://127.0.0.1:8000.
Tài khoản gồm `owner`, `matcha01`, `matcha02`, `mixue01`, `mixue02`.
Mật khẩu chung là `TimezyDemo123`. Demo lưu riêng tại `database/data/demo.sqlite3`.
Demo có ca hiện tại để thử check-in, ca ngày mai đã có người đăng ký và công tháng trước để thử duyệt bổ sung.
Lần chạy tiếp theo giữ dữ liệu đã thao tác.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m backend.app add-user owner "Chủ quán"
.\.venv\Scripts\python.exe -m backend.app add-user matcha01 "Nhân viên Đảo Matcha" --shop 1 --hourly-rate 25000
.\.venv\Scripts\python.exe -m backend.app add-user mixue01 "Nhân viên Mixue" --shop 2 --hourly-rate 25000
.\.venv\Scripts\python.exe -m backend.app serve
```

Yêu cầu Python 3.12. Lệnh tạo tài khoản hỏi mật khẩu tương tác. Dữ liệu nằm trong `database/data/timezy.sqlite3`. Có thể đổi đường dẫn bằng biến môi trường `TIMEZY_DB`. Mở giao diện và API tại `http://127.0.0.1:8000`. Dùng `--host 0.0.0.0` khi cần thử trên điện thoại cùng mạng nội bộ. Môi trường triển khai công khai cần HTTPS và máy chủ HTTP phù hợp cho production.

## API

Gọi `POST /login` với `username` và `password`, sau đó gửi header `Authorization: Bearer <token>`. Các yêu cầu có dữ liệu dùng JSON. Giờ gửi theo ISO 8601 có múi giờ, ví dụ `2026-12-10T17:00:00+07:00`.

| Luồng | API | Vai trò và dữ liệu |
| --- | --- | --- |
| Kết nối | `GET /health` | Không yêu cầu đăng nhập |
| Phiên | `POST /login`, `POST /logout` | Chủ quán hoặc nhân viên |
| Tự đăng ký | `POST /signup` | username, birth_date YYYY-MM-DD, gender male/female/other, email, phone, password, confirm_password, role owner/employee, shop_id khi là nhân viên |
| Duyệt đăng ký | `GET /account-registrations`, `POST /account-registrations/{id}/approve` | Chủ quán xem tài khoản chờ duyệt và cấp hourly_rate cho nhân viên |
| Đổi mật khẩu | `POST /change-password` | Người đã đăng nhập gửi current_password và new_password |
| Tạo mã khôi phục | `POST /recovery-code` | Người đã đăng nhập xác nhận current_password |
| Quên mật khẩu | `POST /reset-password` | username, recovery_code và new_password |
| Hồ sơ đang đăng nhập | `GET /me` | Tên, vai trò và cơ sở của tài khoản |
| Quản lý nhân viên | `GET /employees`, `POST /employees` | Chủ quán tạo tài khoản với name, username, password, shop_id và hourly_rate |
| Cơ sở và thông báo | `GET /shops`, `GET /notifications` | Dữ liệu theo phạm vi tài khoản |
| Mở ca đăng ký | `POST /shifts` | Chủ quán gửi `shop_id`, `starts`, `ends` |
| Xem ca và đăng ký | `GET /shifts`, `POST /shifts/{id}/register` | Nhân viên xem ca và đăng ký tại quán của mình |
| Chọn người và công bố | `GET /shifts/{id}/candidates`, `POST /shifts/{id}/publish` | Chủ quán gửi `employee_ids` gồm ID của những người đã đăng ký ca |
| Đổi giờ ca | `POST /shifts/{id}/reschedule` | Chủ quán gửi `starts`, `ends` trước khi ca bắt đầu và trước khi có người check-in. App thông báo và mở lại đăng ký theo giờ mới |
| Bảng tuần | `GET /weekly?week=current&shop_id=1` | current hoặc next. Nhân viên xem lịch đã công bố của cả quán, dữ liệu công cá nhân dùng API attendance |
| Xác nhận đăng ký tuần sau | `POST /weekly/confirm` | week_start là thứ Hai tuần sau, revision từ submission của GET weekly (0 nếu lần đầu), slots gồm day và slot morning/afternoon/evening/split |
| Giờ bốn ca | `POST /weekly/settings` | Chủ quán gửi shop_id và templates gồm slot, starts, ends HH:MM. Tối full bắt đầu 18:00, tối gãy bắt đầu 20:00 |
| Công bố ca tuần sau | `POST /weekly/publish` | Chủ quán gửi shop_id, day, slot, employee_ids từ những người đã tích đăng ký |
| Lịch và bảng chấm công | `GET /attendance?day=2026-12-10&shop_id=1` | Có thể bỏ bộ lọc. Nhân viên chỉ xem ca của mình |
| Báo chưa có ca | `POST /schedule-issues` | Nhân viên gửi `reason` cho chủ quán |
| Check-in và check-out | `POST /attendance/{id}/check-in`, `POST /attendance/{id}/check-out` | Nhân viên thao tác bằng ID bản ghi chấm công |
| Giải trình | `POST /attendance/{id}/requests` | Nhân viên gửi `kind: "explanation"` và `reason` |
| Bổ sung công | `POST /attendance/{id}/requests` | Nhân viên gửi `kind: "correction"`, `reason`, `check_in`, `check_out` |
| Xem và duyệt yêu cầu | `GET /requests`, `POST /requests/{id}/review` | Chủ quán gửi `approve` dạng boolean và `reason` khi từ chối. Nhân viên xem yêu cầu của mình |
| Xem kỳ và bảng công | `GET /periods`, `GET /periods/{YYYY-MM}` | Nhân viên xem cá nhân. Chủ quán xem tiến độ theo quán và bảng đã xác nhận |
| Xác nhận bảng công | `POST /periods/{YYYY-MM}/confirm` | Nhân viên xác nhận sau khi kiểm tra công và lương |
| Chốt và xuất Excel | `POST /periods/{YYYY-MM}/close`, `GET /periods/{YYYY-MM}/export` | Chủ quán chốt khi đủ xác nhận, sau đó tải Excel có hai sheet |

## Quy tắc đang áp dụng

- Người tự đăng ký chọn Chủ quán / Quản lý hoặc Nhân viên. Tài khoản mới chờ chủ quán duyệt. Khi hệ thống chưa có chủ quán, chủ quán đầu tiên được kích hoạt ngay. Vai trò Chủ quán / Quản lý có quyền quản lý cả hai quán.
- Mọi tài khoản nhân viên mới, gồm tự đăng ký, tạo tại mục Nhân viên và tạo bằng lệnh add-user, đều ở trạng thái pending. Chủ quán duyệt trong mục Nhân viên trước khi nhân viên đăng nhập.
- Đăng ký yêu cầu tên tài khoản, ngày sinh, giới tính, email, số điện thoại, mật khẩu và xác nhận mật khẩu. Email và số điện thoại phải duy nhất. Đăng ký thành công chuyển trực tiếp về trang đăng nhập và điền sẵn tên tài khoản. Mã khôi phục nằm trong phần có thể mở tại trang đăng nhập.
- Ghi nhớ đăng nhập gửi remember=true tới login và giữ token trong localStorage tối đa 30 ngày. Nếu bỏ chọn, phiên lưu trong sessionStorage và hết hạn sau 12 giờ. Đăng xuất xóa token ở cả hai nơi. Mật khẩu không được lưu trong bộ nhớ trình duyệt bởi ứng dụng.
- Quên mật khẩu dùng mã khôi phục ngẫu nhiên cấp khi đăng ký. Tài khoản cũ tạo mã trong mục Tài khoản sau khi xác nhận mật khẩu hiện tại. Mã mới thay thế mã cũ, cần lưu riêng. Sau khi đặt lại mật khẩu, mã được đổi và trả một lần trên giao diện. Phương thức này hoạt động local và không cần dịch vụ email.
- Đổi và đặt lại mật khẩu kết thúc tất cả phiên của tài khoản. Database giữ bản băm mật khẩu, token và mã khôi phục.

- Tác vụ nền mở kỳ từ mùng 9 theo giờ Việt Nam, gửi thông báo trong ứng dụng cho người có ca được công bố trong tháng trước. Server chạy lại sẽ tự xử lý kỳ đến hạn chưa mở.
- Check-in được phép từ giờ bắt đầu đến trước giờ kết thúc ca. Check-out được phép trong giờ ca, gồm đúng mốc kết thúc. Hết ca mà thiếu giờ vào hoặc giờ ra thì nhân viên gửi giải trình kèm giờ thực tế để duyệt bổ sung.
- Trang Ca làm của tôi có nút chấm công ở đầu trang, đồng hồ đồng bộ từ máy chủ và lịch tuần thứ Hai đến Chủ nhật theo giờ Việt Nam. Dữ liệu tự cập nhật mỗi 15 giây và khi quay lại tab. Nút Giải trình xuất hiện ở ca đi muộn hoặc thiếu giờ chấm.
- Đăng ký & xếp ca có hai bảng. Lịch tuần này có nhân viên theo hàng và thứ Hai đến Chủ nhật theo cột. Đăng ký tuần sau có bốn ca theo hàng và bảy ngày theo cột. Nhân viên chọn ca rồi bấm Xác nhận đăng ký. Sau khi gửi, bấm Chỉnh sửa đăng ký và Xác nhận thay đổi để gửi bản mới, hoặc Hủy chỉnh sửa để giữ bản đã gửi. Chủ quán chỉ thấy bản đã xác nhận và chọn người từ từng ô để công bố ca.
- Thay đổi chưa xác nhận nằm trong giao diện. Rời trang có thay đổi sẽ được nhắc. Ca đã công bố được khóa. Xác nhận lại kiểm tra revision để tránh ghi đè thay đổi từ tab khác. Có thể xác nhận không đăng ký ca nào trong tuần.
- Bốn ca mặc định là sáng 07:30–12:00, chiều 12:00–18:00, tối full 18:00–23:30 và tối gãy 20:00–23:30. Chủ quán có thể cấu hình giờ từng quán. Nhân viên có thể đăng ký nhiều lựa chọn, chủ quán sẽ được báo nếu xếp trùng giờ.
- Duyệt giải trình đi muộn loại ca khỏi thống kê đi muộn và giữ giờ chấm. Duyệt bỏ ca chuyển thành vắng có lý do. Ca vắng không phát sinh giờ công.
- Lương tạm tính theo giờ thực tế nhân đơn giá theo giờ, làm tròn đến đồng theo từng ca. Đơn giá được lưu tại thời điểm công bố ca. Ca qua đêm thuộc tháng của giờ bắt đầu.
- Duyệt thay đổi công sẽ yêu cầu nhân viên xác nhận lại nếu họ đã xác nhận. Kỳ đã chốt khóa thao tác chỉnh công.
- Phiên bản này sử dụng thông báo trong ứng dụng. Xác thực tại quán qua QR hoặc GPS, thông báo đẩy, phụ cấp và khấu trừ nằm ngoài phạm vi hiện tại.

Chạy kiểm thử luồng bằng `python -m unittest discover -s backend/tests -v`.
