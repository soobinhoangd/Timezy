# Frontend Timezy

Giao diện web responsive dùng HTML, CSS và JavaScript thuần. Backend phục vụ ba file index.html, styles.css và app.js tại cùng địa chỉ http://127.0.0.1:8000.

Chạy từ thư mục gốc bằng `python -m backend.app serve`. Không cần bước build hoặc npm install.

Nhân viên có thể đăng ký ca, xem ca đã xếp, chấm công, gửi giải trình và bổ sung công, xem thông báo, xác nhận bảng công và lương.

Chủ quán có thể tạo nhân viên, mở ca, chọn người đã đăng ký, đổi giờ ca, theo dõi công, duyệt yêu cầu, kiểm tra xác nhận, chốt kỳ và tải Excel.

Các trường ngày giờ được nhập theo giờ Việt Nam. Chọn ghi nhớ để lưu phiên 30 ngày trong localStorage, hoặc bỏ chọn để dùng sessionStorage với phiên 12 giờ. Đăng xuất hoặc hết phiên sẽ xóa token khỏi cả hai nơi.

Trang đăng nhập có Đăng ký và Quên mật khẩu. Mục Tài khoản cho phép đổi mật khẩu và tạo mã khôi phục. Chủ quán duyệt người tự đăng ký tại mục Nhân viên.

Trang Tài khoản có avatar, tên, email, cơ sở và ngôn ngữ Tiếng Việt. Thông tin cơ bản mở hồ sơ cá nhân cùng mã nhân viên, lương theo giờ và ngày gia nhập. Có thể cập nhật dữ liệu cá nhân và đổi ảnh. Các thiết lập mật khẩu nằm trong mục Bảo mật tài khoản có thể mở rộng.

Đổi ca được gửi từ thẻ ca hoặc lịch tuần. Chọn nhân viên cùng quán đủ điều kiện, sau đó người nhận xác nhận trong trang chủ hoặc Thông báo. Lịch tuần hiện tại tự tải lại mỗi 15 giây. Trang chủ cập nhật ca và yêu cầu đổi mỗi 15 giây hoặc khi quay lại tab.

Đăng ký & xếp ca có thanh Lịch tuần này và Đăng ký lịch tuần sau. Nhân viên xem lịch của cả quán trong tuần hiện tại, tích ca sáng, chiều, tối full từ 18h hoặc tối gãy từ 20h cho tuần tiếp theo, sau đó bấm Xác nhận đăng ký. Để thay đổi, bấm Chỉnh sửa đăng ký rồi Xác nhận thay đổi hoặc Hủy chỉnh sửa. Chủ quán nhận các lựa chọn đã xác nhận và chọn người để công bố từng ca. Bảng tuần có thể cuộn ngang trên điện thoại.
