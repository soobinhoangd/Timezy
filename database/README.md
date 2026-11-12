# Database Timezy

- `schema.sql` định nghĩa bảng, khóa ngoại và chỉ mục.
- `connection.py` quản lý kết nối và khởi tạo schema.
- `data/timezy.sqlite3` lưu dữ liệu chạy thực tế và được tạo khi khởi động.

Backend gọi initialize trước khi nhận yêu cầu. Khởi tạo nhiều lần giữ dữ liệu đang có, bổ sung bảng và chỉ mục còn thiếu. Phiên bản schema hiện tại là 6 qua SQLite user_version. Bản 2 thêm account_profiles cho vai trò, trạng thái duyệt và bản băm mã khôi phục. Bản 3 thêm trigger đặt mọi nhân viên mới thành pending ngay khi tạo trong users. Tài khoản đã tồn tại trước khi nâng cấp giữ trạng thái duyệt.

Các nhóm dữ liệu gồm shops và users cho tài khoản, shifts và registrations cho đăng ký ca, attendance và requests cho công cùng lịch sử xử lý, periods và statements cho xác nhận tháng, sessions và notifications cho phiên cùng thông báo.

Schema phiên bản 4 thêm account_details để lưu ngày sinh, giới tính, email và số điện thoại của người tự đăng ký. Email và số điện thoại có ràng buộc duy nhất. Dữ liệu tài khoản cũ tiếp tục được giữ, thông tin chưa thu thập có thể chưa có trong account_details.

Phiên bản 5 thêm shift_templates cấu hình bốn ca theo cơ sở, weekly_availability lưu các ô đăng ký của tuần sau và weekly_slots liên kết ô lịch với ca đã công bố. Lựa chọn đăng ký được giữ độc lập với giờ cấu hình cho đến khi chủ quán công bố ca.

Phiên bản 6 thêm weekly_submissions để ghi thời điểm xác nhận và revision của đăng ký theo nhân viên và tuần. Các lựa chọn từ phiên bản cũ được chuyển thành bản đã xác nhận. Bản mới chỉ ghi weekly_availability khi người dùng xác nhận cả tuần. Chỉnh sửa được lưu nguyên tử và kiểm tra revision cùng các ca đã công bố.

Có thể đặt TIMEZY_DB đến một file SQLite khác. Đường dẫn tương đối được tính từ thư mục chạy lệnh. Sao lưu khi ứng dụng dừng bằng cách chép file SQLite, hoặc dùng SQLite backup API khi ứng dụng đang chạy. Không đưa file dữ liệu vào Git.
