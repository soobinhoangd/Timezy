# Frontend Vercel + backend/database Railway

## Kiến trúc

- Vercel phục vụ HTML, CSS, JavaScript trong thư mục frontend qua CDN.
- Trình duyệt gọi `/api/...` trên cùng domain Vercel. frontend/vercel.json chuyển tiếp tới `https://timezy-production.up.railway.app/...` và giữ phương thức, body, query, Authorization.
- Railway chạy backend Docker/Waitress và SQLite trên volume `/var/data`. Giữ một replica và Serverless tắt.
- Dữ liệu tài khoản, công và lương không cache. Tài nguyên giao diện được cache CDN, trình duyệt kiểm tra lại khi tải.

Không cần mở CORS hoặc đặt token/mật khẩu database vào Vercel. Frontend dùng Bearer token như trước. Khi chuyển domain, người dùng đăng nhập lại do bộ nhớ trình duyệt tách theo domain.

## Triển khai

1. Commit và push các thay đổi lên GitHub. Backend mới hỗ trợ cả `/api/...` và các URL cũ, nên vẫn chạy local và trên domain Railway. Vercel chuyển tiếp bỏ `/api` nên tương thích cả backend đang chạy trước lần cập nhật này.
2. Trong https://vercel.com/new, Import repository soobinhoangd/Timezy.
3. Chọn Framework Preset **Other**, Root Directory **frontend**.
4. Không đặt Install Command/Build Command. Output Directory là `.` (đã có trong frontend/vercel.json). Không chọn root repository vì có backend Python.
5. Deploy, lấy URL HTTPS do Vercel cấp. frontend/vercel.json nằm trong Root Directory nên được Vercel đọc trực tiếp.
6. Kiểm tra URL `/api/health` trả `{"ok":true}`, mở giao diện, đăng nhập, xem lịch, thử gửi yêu cầu và tải Excel bằng tài khoản phù hợp.
7. Gắn URL frontend Vercel thật vào GitHub About/Website và README khi đã kiểm tra. Giữ URL Railway để backend tiếp tục hoạt động.

Vercel không cần thư viện Python hoặc volume. Không thay đổi TIMEZY_DB và không xóa volume Railway. Nếu đổi tên miền backend, cập nhật destination trong frontend/vercel.json rồi deploy lại frontend.

## Kiểm tra tốc độ

CDN có thể giảm thời gian tải giao diện; tốc độ API vẫn phụ thuộc Railway và database. Proxy thêm một chặng mạng, không bảo đảm mọi thao tác nhanh hơn. Dùng DevTools Network đo tải trang và API sau khi deploy. Railway hiện đặt US West; có thể cân nhắc vùng gần người dùng sau khi sao lưu và kiểm tra việc di chuyển volume, không tự di chuyển dữ liệu đang chạy.

## Docker

Dockerfile tại gốc repository đóng gói backend, thư viện và frontend dự phòng. Railway đã build và chạy image này. Dữ liệu thật không nằm trong image; `.dockerignore` loại SQLite, secrets và runtime local. Lệnh chạy là `python -m backend.deploy`; cổng lấy từ PORT của Railway.

## Tài liệu

- https://vercel.com/docs/routing/rewrites
- https://vercel.com/docs/project-configuration/vercel-json
- https://docs.railway.com/volumes
