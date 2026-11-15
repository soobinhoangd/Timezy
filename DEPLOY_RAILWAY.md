# Triển khai Timezy trên Railway

Ứng dụng chạy một service Docker gồm frontend, API và SQLite. Dockerfile đã chạy Waitress qua `python -m backend.deploy`, lắng nghe `0.0.0.0` và biến `PORT` của nền tảng.

## 1. Đưa mã nguồn lên GitHub

Tại thư mục D:\Timezy, commit các thay đổi rồi push nhánh main lên repository https://github.com/soobinhoangd/Timezy. Không đưa database local hoặc mật khẩu vào Git.

## 2. Tạo service

1. Đăng nhập https://railway.com bằng GitHub.
2. Chọn New Project → Deploy from GitHub repo → soobinhoangd/Timezy, nhánh main. Cấp quyền truy cập repository nếu được hỏi.
3. Giữ Root Directory tại gốc repository để Railway tìm Dockerfile. Không cần Build Command hay Start Command tùy chỉnh.
4. Nếu lượt deploy tự động đầu tiên báo thiếu thông tin chủ quán, hoàn thành các bước dưới rồi deploy lại.

## 3. Gắn volume trước khi sử dụng

Tạo volume gắn vào service Timezy, Mount Path là `/var/data`. File SQLite cùng WAL/SHM phải nằm trên volume này để tồn tại qua restart và redeploy. Dùng một replica cho SQLite.

Trong tab Variables của service, thêm:

| Biến | Giá trị |
| --- | --- |
| TIMEZY_DB | /var/data/timezy.sqlite3 |
| TIMEZY_ADMIN_USERNAME | chuquan hoặc tên đăng nhập bạn chọn |
| TIMEZY_ADMIN_PASSWORD | Mật khẩu riêng từ 12 đến 256 ký tự |

Nhập mật khẩu trực tiếp trên Railway, không commit vào repository. PORT do Railway cấp; ứng dụng tự đọc, không cần đặt lại.

## 4. Bật dịch vụ và lấy link

1. Trong Settings → Deploy, đặt Healthcheck Path là `/health`.
2. Tắt Serverless/App Sleep để service tiếp tục chạy khi không có người truy cập; tác vụ gửi thông báo kỳ công cần máy chủ hoạt động.
3. Kiểm tra gói, hạn mức và chi phí tài khoản để duy trì dịch vụ. Thời gian dùng thử không bảo đảm chạy lâu dài.
4. Deploy các thay đổi. Khi service hoạt động, vào Settings → Networking → Public Networking → Generate Domain. Chọn cổng Railway phát hiện cho tiến trình Python (bản triển khai hiện tại là 8080). Không suy ra target port chỉ từ EXPOSE trong Dockerfile; Railway có thể cấp PORT khác lúc chạy.
5. Mở URL HTTPS Railway cấp và đăng nhập bằng tài khoản chủ quán trong Variables.

Tài khoản chủ quán được tạo trước khi server nhận yêu cầu. Sau khi database đã có chủ quán, thay đổi các biến khởi tạo không đặt lại mật khẩu. Đổi mật khẩu qua ứng dụng.

## 5. Kiểm tra và gắn GitHub

- Mở `/health`, kiểm tra đăng nhập và tạo/duyệt tài khoản nhân viên.
- Restart service, đăng nhập lại và kiểm tra dữ liệu vẫn còn.
- Thêm URL thật vào phần About → Website của repository GitHub và README: `[Mở Timezy](URL_HTTPS_RAILWAY_CAP)`.
- Giữ volume khi redeploy; thiết lập sao lưu định kỳ. Service có volume có thể gián đoạn ngắn khi redeploy.

Bản cloud bắt đầu với database mới; tài khoản và dữ liệu demo local không được đưa lên image. Nếu cần chuyển dữ liệu thật, dùng bản sao lưu SQLite và chuyển vào volume khi service dừng.

## Tài liệu Railway

- https://docs.railway.com/services
- https://docs.railway.com/volumes
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/networking/domains/working-with-domains
- https://docs.railway.com/pricing/cost-control

Cấu hình service thực hiện trong dashboard; Dockerfile hiện tại dùng trực tiếp được. Không cần railway.toml/railway.json cho luồng triển khai này.
