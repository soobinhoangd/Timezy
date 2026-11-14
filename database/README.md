# Database Timezy

- `schema.sql` định nghĩa bảng, khóa ngoại và chỉ mục.
- `connection.py` quản lý kết nối và khởi tạo schema.
- `data/timezy.sqlite3` lưu dữ liệu chạy thực tế và được tạo khi khởi động.

Backend gọi initialize trước khi nhận yêu cầu. Khởi tạo nhiều lần giữ dữ liệu đang có, bổ sung bảng và chỉ mục còn thiếu. Phiên bản schema hiện tại là 9 qua SQLite user_version. Bản 2 thêm account_profiles cho vai trò, trạng thái duyệt và bản băm mã khôi phục. Bản 3 thêm trigger đặt mọi nhân viên mới thành pending ngay khi tạo trong users. Tài khoản đã tồn tại trước khi nâng cấp giữ trạng thái duyệt.

Các nhóm dữ liệu gồm shops và users cho tài khoản, shifts và registrations cho đăng ký ca, attendance và requests cho công cùng lịch sử xử lý, periods và statements cho xác nhận tháng, sessions và notifications cho phiên cùng thông báo.

Schema phiên bản 4 thêm account_details để lưu ngày sinh, giới tính, email và số điện thoại của người tự đăng ký. Email và số điện thoại có ràng buộc duy nhất. Dữ liệu tài khoản cũ tiếp tục được giữ, thông tin chưa thu thập có thể chưa có trong account_details.

Phiên bản 5 thêm shift_templates cấu hình bốn ca theo cơ sở, weekly_availability lưu các ô đăng ký của tuần sau và weekly_slots liên kết ô lịch với ca đã công bố. Lựa chọn đăng ký được giữ độc lập với giờ cấu hình cho đến khi chủ quán công bố ca.

Phiên bản 6 thêm weekly_submissions để ghi thời điểm xác nhận và revision của đăng ký theo nhân viên và tuần. Các lựa chọn từ phiên bản cũ được chuyển thành bản đã xác nhận. Bản mới chỉ ghi weekly_availability khi người dùng xác nhận cả tuần. Chỉnh sửa được lưu nguyên tử và kiểm tra revision cùng các ca đã công bố.

Phiên bản 7 thêm shift_transfers lưu người gửi, người nhận, trạng thái, thời điểm gửi và phản hồi. Chỉ một yêu cầu pending cho một bản ghi attendance. Đồng ý đổi ca cập nhật người sở hữu attendance cùng đơn giá của người nhận, đồng thời cập nhật registrations trong giao dịch POST. Lịch tuần đọc attendance nên phản ánh người làm mới. Khi chủ quán đổi giờ và xóa bản ghi xếp ca, lịch sử đổi ca được giữ với attendance_id rỗng.

Phiên bản 8 thêm trigger chặn tạo hoặc chuyển bản ghi attendance vào ca đã có người. API công bố lịch kiểm tra thêm vị trí sáng, chiều, full hoặc gãy trong cùng ngày và quán, để chặn tạo hai lịch riêng cho cùng vị trí.

Phiên bản 9 thêm employee_metadata cho mã nhân viên, CCCD, ngày gia nhập, avatar và ngôn ngữ. Mã được cấp bằng trigger khi tạo người dùng và bổ sung cho tài khoản cũ khi nâng cấp. Ngày gia nhập cũ chưa biết để trống, tài khoản mới ghi ngày kích hoạt. Thông tin sinh và liên hệ tiếp tục lưu trong account_details, đơn giá trong users. Hồ sơ công khai trong lịch tuần không chứa CCCD hoặc thông tin liên hệ.

Có thể đặt TIMEZY_DB đến một file SQLite khác. Đường dẫn tương đối được tính từ thư mục chạy lệnh. Sao lưu khi ứng dụng dừng bằng cách chép file SQLite, hoặc dùng SQLite backup API khi ứng dụng đang chạy. Không đưa file dữ liệu vào Git.
