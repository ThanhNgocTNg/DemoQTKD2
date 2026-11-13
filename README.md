# AI Agent Xử lý Cơ hội Bán hàng B2B — Công ty Minh An

Ứng dụng web AI Agent hỗ trợ quy trình tiếp nhận, thẩm định, lập đề xuất kinh doanh và theo dõi cơ hội B2B cho **Công ty Công nghệ Minh An** (đội ngũ 6 Nhân viên Kinh doanh, xử lý ~180 yêu cầu/tuần).

## Tính năng chính

1. **Đầu vào linh hoạt (Google Sheets / CSV / XLSX / Nhập trực tiếp)**:
   - Tải lên file `.xlsx` nhiều sheet hoặc các file `.csv` riêng lẻ (`Yêu cầu khách hàng`, `Sản phẩm & Giá`, `Tồn kho & Triển khai`, `Chính sách chiết khấu`, `Nhân viên Kinh doanh`).
   - Dán trực tiếp **link Google Sheets** (hỗ trợ cả workbook nhiều tab hoặc tab theo `gid`, chỉ cần mở quyền *"Bất kỳ ai có đường liên kết đều có thể xem"*).
   - Có sẵn bộ file mẫu trong thư mục `sample_data/` và nút tải về trực tiếp trên giao diện.

2. **Quy trình xử lý chuẩn theo sơ đồ Công ty Minh An**:
   - **Bắt đầu: Tiếp nhận yêu cầu** → **Phân loại & Kiểm tra thông tin** → **Có đủ thông tin?**:
     - **Không**: Chuyển nhánh **Yêu cầu KH làm rõ / bổ sung**, gán bắt buộc **Người theo dõi** (NVKD phụ trách + lịch nhắc SLA để không bị thất lạc hồ sơ thiếu ngân sách / chưa rõ người duyệt), tạo bản nháp email hỏi lại và cho phép nhập thông tin bổ sung để chạy lại vòng lặp quy trình.
     - **Có**: **Tạo Hồ sơ Cơ hội & Gán người phụ trách** (cân bằng tải cho 6 NVKD theo chuyên môn) → **Thẩm định tồn kho & giá (NVKD & Bộ phận Vận hành)** → **Lập Báo giá & Dự thảo đề xuất**.
   - **Có vượt thẩm quyền / Cần chiết khấu đặc biệt?**:
     - **Có**: Chuyển **Trưởng phòng duyệt** ngay trên giao diện (có thể duyệt, điều chỉnh % chiết khấu hoặc trả lại thương lượng).
     - **Không**: Chuyển thẳng tới **Kết thúc: Cập nhật & Theo dõi**.

3. **Ngăn chặn 4 rủi ro vận hành cốt lõi**:
   - **Không bỏ sót hạng mục**: Tách và đối chiếu toàn bộ sản phẩm/dịch vụ trong văn bản; hạng mục chưa có SKU chuẩn vẫn được giữ lại và đánh dấu riêng.
   - **Không dùng giá cũ**: Áp dụng đơn giá theo phiên bản bảng giá hiện hành mới nhất và cảnh báo khi khách hàng dẫn giá cũ.
   - **Không hứa thời hạn bất khả thi**: Tính thời gian đáp ứng thực tế (`nhập hàng bổ sung nếu thiếu tồn + thời gian triển khai kỹ thuật`) so với hạn khách hàng yêu cầu, đề xuất giao hàng chia đợt hoặc mã thay thế có sẵn.
   - **Không mất dấu người theo dõi**: 100% hồ sơ (kể cả thiếu ngân sách/người duyệt) đều có người phụ trách và lịch theo dõi SLA.

4. **Kết quả trả trực tiếp trên giao diện & Xuất báo cáo**:
   - Hiển thị sơ đồ quy trình tương tác, chỉ số điều hành cho Ban Giám đốc, bảng thẩm định giá & tồn kho từng hạng mục, các đề xuất kinh doanh tối ưu và bản nháp phản hồi khách hàng.
   - Hỗ trợ xuất toàn bộ kết quả ra `.xlsx` nhiều sheet hoặc `.csv`.

## Cách khởi chạy

Yêu cầu: Python 3.9+ (không cần cài thêm thư viện ngoài).

```bash
chmod +x start.sh
./start.sh
```

Hoặc chạy trực tiếp:

```bash
python3 app.py --open
```

Mặc định ứng dụng chạy tại `http://127.0.0.1:8080`.

