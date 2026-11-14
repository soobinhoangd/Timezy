# Triển khai Timezy trên Render

Cấu hình triển khai gồm web service Docker với Waitress, ổ đĩa SQLite 1 GB và tài khoản chủ quán khởi tạo từ biến môi trường. Dịch vụ và ổ đĩa dùng gói trả phí. Kiểm tra chi phí Render hiển thị trước khi xác nhận tạo dịch vụ.

## Đẩy mã nguồn

Đưa Dockerfile, render.yaml và các thay đổi backend trong đợt này lên nhánh main của repository https://github.com/soobinhoangd/Timezy.

## Tạo dịch vụ

1. Tạo tài khoản tại https://dashboard.render.com bằng GitHub.
2. Mở https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fsoobinhoangd%2FTimezy hoặc chọn New rồi Blueprint và chọn repository Timezy.
3. Nếu repository riêng tư, cấp quyền cho Render truy cập repository đó.
4. Đặt TIMEZY_ADMIN_USERNAME bằng tên tài khoản chủ quán muốn dùng, ví dụ chuquan.
5. Đặt TIMEZY_ADMIN_PASSWORD bằng mật khẩu riêng từ 12 đến 256 ký tự.
6. Kiểm tra gói web service và ổ đĩa, rồi xác nhận triển khai.
7. Khi service có trạng thái Live, mở URL Render hiển thị và đăng nhập bằng hai giá trị đã nhập.

Biến TIMEZY_DB đã được cấu hình là /var/data/timezy.sqlite3. Ổ đĩa gắn tại /var/data lưu cả file SQLite và các file WAL/SHM. Dùng một instance cho database này.

Máy chủ tạo tài khoản chủ quán trước khi nhận yêu cầu đầu tiên. Khi khởi động lại, tài khoản và mật khẩu đã có trong database tiếp tục được dùng. Thay đổi biến khởi tạo không đặt lại mật khẩu của tài khoản đang tồn tại. Dùng chức năng đổi hoặc khôi phục mật khẩu của ứng dụng để thay mật khẩu.

Bản triển khai mới bắt đầu bằng database riêng. Dữ liệu local và các tài khoản demo không được đóng gói trong Docker image. Người dùng đăng ký qua URL công khai và chờ chủ quán duyệt. Nếu cần chuyển dữ liệu hiện có, sao lưu SQLite và chuyển bản sao vào ổ đĩa trong lúc service dừng.

## Gắn URL vào GitHub

Sau khi deploy thành công, thêm liên kết vào README với URL thật do Render cấp.

```markdown
[Mở ứng dụng Timezy](DAN_URL_RENDER_VAO_DAY)
```

Mỗi lần cập nhật mã nguồn, Render có thể triển khai lại từ nhánh main. Ổ đĩa riêng giữ dữ liệu qua các lần deploy và restart. Có thể đặt tên miền riêng sau trong trang Settings của service.

## Kiểm tra vận hành

- Mở /health để kiểm tra service phản hồi.
- Đăng nhập, tạo tài khoản nhân viên, duyệt và kiểm tra ca làm.
- Khởi động lại service rồi xác nhận dữ liệu vẫn còn.
- Sao lưu SQLite định kỳ bằng SQLite backup API hoặc snapshot của ổ đĩa.

## Tài liệu nền tảng

- https://render.com/docs/deploy-to-render
- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks
- https://render.com/docs/free
