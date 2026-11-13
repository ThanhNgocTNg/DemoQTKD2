"""Realistic B2B sample datasets and template generators for Minh An Company."""

from __future__ import annotations

import csv
import io
import os
from typing import Any, Dict, List, Tuple

from agent.parsers import build_xlsx_bytes


def get_default_catalog() -> List[Dict[str, Any]]:
    """Return Minh An's current active product & service catalog (Price List 11/2026)."""
    return [
        {
            "sku": "LAP-DELL-5440",
            "name": "Laptop Dell Latitude 5440 (i5-1335U / 16GB / 512GB)",
            "category": "Thiết bị đầu cuối",
            "unit": "Chiếc",
            "aliases": ["laptop dell latitude 5440", "dell latitude 5440", "laptop dell 5440", "latitude 5440"],
            "current_price": 19_900_000,
            "old_price": 18_500_000,
            "cost_price": 16_200_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 45,
            "restock_days": 7,
            "deploy_days": 2,
        },
        {
            "sku": "LAP-LEN-X1C",
            "name": "Laptop Lenovo ThinkPad X1 Carbon Gen 12",
            "category": "Thiết bị đầu cuối",
            "unit": "Chiếc",
            "aliases": ["thinkpad x1 carbon", "lenovo thinkpad x1", "laptop thinkpad x1"],
            "current_price": 38_500_000,
            "old_price": 37_000_000,
            "cost_price": 31_800_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 18,
            "restock_days": 10,
            "deploy_days": 2,
        },
        {
            "sku": "MON-DELL-P2425H",
            "name": "Màn hình Dell P2425H 24 inch FHD IPS",
            "category": "Thiết bị đầu cuối",
            "unit": "Chiếc",
            "aliases": ["man hinh dell p2425h", "dell p2425h", "man hinh dell 24"],
            "current_price": 4_450_000,
            "old_price": 4_450_000,
            "cost_price": 3_600_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 60,
            "restock_days": 5,
            "deploy_days": 1,
        },
        {
            "sku": "PER-LOGI-MK295",
            "name": "Bộ bàn phím & chuột không dây Logitech MK295",
            "category": "Thiết bị đầu cuối",
            "unit": "Bộ",
            "aliases": ["ban phim chuot logitech", "logitech mk295", "bo ban phim chuot"],
            "current_price": 890_000,
            "old_price": 890_000,
            "cost_price": 680_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 120,
            "restock_days": 3,
            "deploy_days": 1,
        },
        {
            "sku": "FW-FG-60F",
            "name": "Thiết bị tường lửa FortiGate 60F (kèm License 1 năm)",
            "category": "Hạ tầng mạng & Bảo mật",
            "unit": "Bộ",
            "aliases": ["fortigate 60f", "tuong lua fortigate 60f", "firewall fortigate 60f"],
            "current_price": 24_500_000,
            "old_price": 22_800_000,
            "cost_price": 19_500_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 8,
            "restock_days": 10,
            "deploy_days": 3,
        },
        {
            "sku": "FW-FG-100F",
            "name": "Thiết bị tường lửa FortiGate 100F Enterprise",
            "category": "Hạ tầng mạng & Bảo mật",
            "unit": "Bộ",
            "aliases": ["fortigate 100f", "tuong lua fortigate 100f", "firewall fortigate 100f"],
            "current_price": 68_000_000,
            "old_price": 65_000_000,
            "cost_price": 54_000_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 4,
            "restock_days": 12,
            "deploy_days": 4,
        },
        {
            "sku": "SW-CISCO-9200",
            "name": "Switch Cisco Catalyst 9200L 24-Port PoE+",
            "category": "Hạ tầng mạng & Bảo mật",
            "unit": "Bộ",
            "aliases": ["switch cisco 9200", "cisco catalyst 9200", "switch cisco catalyst 9200"],
            "current_price": 32_000_000,
            "old_price": 30_500_000,
            "cost_price": 25_600_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 24,
            "restock_days": 12,
            "deploy_days": 3,
        },
        {
            "sku": "SW-ARUBA-6100",
            "name": "Switch Aruba CX 6100 24G PoE+",
            "category": "Hạ tầng mạng & Bảo mật",
            "unit": "Bộ",
            "aliases": ["switch aruba 6100", "aruba 6100", "switch aruba"],
            "current_price": 21_500_000,
            "old_price": 21_500_000,
            "cost_price": 17_100_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 30,
            "restock_days": 8,
            "deploy_days": 2,
        },
        {
            "sku": "WIFI-ARUBA-AP22",
            "name": "Bộ phát Wi-Fi 6 Aruba Instant On AP22",
            "category": "Hạ tầng mạng & Bảo mật",
            "unit": "Bộ",
            "aliases": ["wifi aruba ap22", "aruba ap22", "access point aruba"],
            "current_price": 4_950_000,
            "old_price": 4_950_000,
            "cost_price": 3_800_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 35,
            "restock_days": 5,
            "deploy_days": 2,
        },
        {
            "sku": "SRV-HPE-DL380",
            "name": "Máy chủ HPE ProLiant DL380 Gen11 (Xeon / 64GB / 2x1.2TB)",
            "category": "Máy chủ & Phần mềm Cloud",
            "unit": "Bộ",
            "aliases": ["hpe proliant dl380", "may chu hpe dl380", "server hpe dl380", "dl380 gen11"],
            "current_price": 115_000_000,
            "old_price": 108_000_000,
            "cost_price": 93_000_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 3,
            "restock_days": 10,
            "deploy_days": 4,
        },
        {
            "sku": "SRV-DELL-R550",
            "name": "Máy chủ Dell PowerEdge R550 (Xeon / 64GB)",
            "category": "Máy chủ & Phần mềm Cloud",
            "unit": "Bộ",
            "aliases": ["dell poweredge r550", "may chu dell r550", "server dell r550"],
            "current_price": 96_000_000,
            "old_price": 96_000_000,
            "cost_price": 77_000_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 10,
            "restock_days": 9,
            "deploy_days": 4,
        },
        {
            "sku": "SW-M365-BP",
            "name": "Bản quyền Microsoft 365 Business Premium (1 năm)",
            "category": "Máy chủ & Phần mềm Cloud",
            "unit": "License",
            "aliases": ["microsoft 365 business premium", "ban quyen microsoft 365", "m365 business", "license m365"],
            "current_price": 5_800_000,
            "old_price": 5_400_000,
            "cost_price": 4_750_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 9999,
            "restock_days": 1,
            "deploy_days": 2,
        },
        {
            "sku": "SVC-DEPLOY-LAN",
            "name": "Gói triển khai & cấu hình hạ tầng mạng LAN/Firewall văn phòng",
            "category": "Dịch vụ triển khai",
            "unit": "Gói",
            "aliases": ["trien khai mang lan", "cau hinh mang lan", "goi trien khai mang", "lap dat mang", "cau hinh he thong"],
            "current_price": 18_000_000,
            "old_price": 16_000_000,
            "cost_price": 10_500_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 999,
            "restock_days": 0,
            "deploy_days": 3,
        },
        {
            "sku": "SVC-M365-MIG",
            "name": "Dịch vụ triển khai & chuyển đổi dữ liệu Microsoft 365",
            "category": "Dịch vụ triển khai",
            "unit": "Gói",
            "aliases": ["trien khai microsoft 365", "dich vu trien khai microsoft 365", "cai dat microsoft 365", "chuyen doi microsoft 365", "trien khai m365", "migration m365"],
            "current_price": 15_000_000,
            "old_price": 15_000_000,
            "cost_price": 8_500_000,
            "price_version": "Bảng giá 11/2026",
            "stock": 999,
            "restock_days": 0,
            "deploy_days": 4,
        },
    ]


def get_default_policy() -> Dict[str, Any]:
    """Return Minh An's discount & escalation policy."""
    tiers = [
        {
            "rule_id": "POL-01",
            "rule_name": "Đơn hàng Tiêu chuẩn (< 300 triệu)",
            "min_order_value": 0,
            "max_order_value": 299_999_999,
            "max_rep_discount": 4.0,
            "max_manager_discount": 10.0,
            "approver_role": "Trưởng phòng Kinh doanh",
            "notes": "NVKD tự duyệt tối đa 4%. Từ >4% đến 10% trình Trưởng phòng KD; >10% trình Ban Giám đốc.",
        },
        {
            "rule_id": "POL-02",
            "rule_name": "Đơn hàng Doanh nghiệp (300 triệu – 1 tỷ)",
            "min_order_value": 300_000_000,
            "max_order_value": 1_000_000_000,
            "max_rep_discount": 5.0,
            "max_manager_discount": 12.0,
            "approver_role": "Trưởng phòng Kinh doanh",
            "notes": "NVKD tự duyệt tối đa 5%. Từ >5% đến 12% trình Trưởng phòng KD; >12% trình Ban Giám đốc.",
        },
        {
            "rule_id": "POL-03",
            "rule_name": "Đơn hàng Dự án lớn (> 1 tỷ)",
            "min_order_value": 1_000_000_001,
            "max_order_value": None,
            "max_rep_discount": 5.0,
            "max_manager_discount": 12.0,
            "approver_role": "Trưởng phòng Kinh doanh & Ban Giám đốc",
            "notes": "Mọi đơn hàng > 1 tỷ bắt buộc qua thẩm định Trưởng phòng Kinh doanh trước khi phát hành.",
        },
    ]
    return {
        "default_rep_max_discount": 5.0,
        "default_manager_max_discount": 12.0,
        "max_rep_order_value": 1_000_000_000,
        "min_margin_percent": 11.0,
        "tiers": tiers,
    }


def get_default_sales_team() -> List[Dict[str, Any]]:
    """Return Minh An's 6 B2B Sales Representatives handling ~180 requests/week."""
    return [
        {
            "rep_id": "NVKD-01",
            "name": "Nguyễn Minh Tuấn",
            "specialty": "Thiết bị đầu cuối & Văn phòng",
            "active_deals": 26,
            "weekly_capacity": 32,
            "email": "tuan.nm@minhan.vn",
        },
        {
            "rep_id": "NVKD-02",
            "name": "Trần Thu Hà",
            "specialty": "Hạ tầng mạng & Bảo mật",
            "active_deals": 24,
            "weekly_capacity": 30,
            "email": "ha.tt@minhan.vn",
        },
        {
            "rep_id": "NVKD-03",
            "name": "Lê Hoàng Nam",
            "specialty": "Máy chủ & Phần mềm Cloud",
            "active_deals": 25,
            "weekly_capacity": 30,
            "email": "nam.lh@minhan.vn",
        },
        {
            "rep_id": "NVKD-04",
            "name": "Phạm Khánh Linh",
            "specialty": "Giải pháp CNTT tổng hợp",
            "active_deals": 23,
            "weekly_capacity": 30,
            "email": "linh.pk@minhan.vn",
        },
        {
            "rep_id": "NVKD-05",
            "name": "Đỗ Quốc Việt",
            "specialty": "Hạ tầng mạng & Dịch vụ triển khai",
            "active_deals": 27,
            "weekly_capacity": 32,
            "email": "viet.dq@minhan.vn",
        },
        {
            "rep_id": "NVKD-06",
            "name": "Vũ Ngọc Anh",
            "specialty": "Thiết bị đầu cuối & Cloud",
            "active_deals": 22,
            "weekly_capacity": 30,
            "email": "anh.vn@minhan.vn",
        },
    ]


def get_sample_requests() -> List[Dict[str, Any]]:
    """Return 12 realistic B2B customer requests covering every Minh An scenario & edge case."""
    return [
        {
            "request_id": "REQ-2026-001",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Công ty CP Logistics Hải Phong",
            "contact_name": "chị Hương - P. Hành chính (huong@haiphonglog.vn)",
            "approver": "Ông Trần Quốc Tuấn - Giám đốc CNTT",
            "request_text": (
                "Chào Minh An, Công ty CP Logistics Hải Phong cần báo giá cho đợt nâng cấp văn phòng mới:\n"
                "- 12 Laptop Dell Latitude 5440\n"
                "- 12 Màn hình Dell P2425H\n"
                "- 01 Gói triển khai & cấu hình hạ tầng mạng LAN văn phòng\n"
                "Ngân sách tổng dự kiến 330 triệu đồng. Thời hạn cần bàn giao hoàn tất trong 7 ngày tới. "
                "Đề nghị chiết khấu 4%. Người phê duyệt: Ông Trần Quốc Tuấn - Giám đốc CNTT."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-002",
            "received_date": "2026-11-11",
            "channel": "Biểu mẫu Web",
            "customer_name": "Công ty TNHH Sản xuất Nam Việt",
            "contact_name": "anh Dũng (dung.it@namviet.vn)",
            "approver": "Bà Lê Thị Mai - Phó Tổng Giám đốc",
            "request_text": (
                "Bên Công ty TNHH Sản xuất Nam Việt cần đầu tư hệ thống mạng cho 2 nhà xưởng:\n"
                "- 15 Switch Cisco Catalyst 9200\n"
                "- 04 Thiết bị tường lửa FortiGate 60F\n"
                "- 20 Bộ phát Wi-Fi 6 Aruba Instant On AP22\n"
                "- 01 Gói triển khai & cấu hình hạ tầng mạng LAN văn phòng\n"
                "Ngân sách tối đa 700 triệu VNĐ. Mong muốn hoàn thành trong 14 ngày. "
                "Vì lấy gói lớn nên đề nghị Minh An chiết khấu 9%. Người duyệt: Bà Lê Thị Mai - Phó Tổng Giám đốc."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-003",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Công ty CP Dược phẩm Bình Minh",
            "contact_name": "anh Quang (quang@binhminhpharma.vn)",
            "approver": "Ông Nguyễn Văn Long - Tổng Giám đốc",
            "request_text": (
                "Công ty CP Dược phẩm Bình Minh cần gấp:\n"
                "- 08 Máy chủ HPE ProLiant DL380 Gen11\n"
                "- 10 Switch Cisco Catalyst 9200\n"
                "Ngân sách dự kiến 1.2 tỷ đồng. Cần giao hàng và lắp đặt gấp trong vòng 4 ngày để kịp chạy ERP. "
                "Xin mức chiết khấu đặc biệt 14%. Người phê duyệt: Ông Nguyễn Văn Long - Tổng Giám đốc."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-004",
            "received_date": "2026-11-11",
            "channel": "Biểu mẫu Web",
            "customer_name": "Công ty TNHH Thương mại An Thịnh",
            "contact_name": "chị Lan (lan.nt@anthinh.com.vn)",
            "approver": "",
            "request_text": (
                "Chào bạn, Công ty TNHH Thương mại An Thịnh muốn hỏi báo giá 15 Laptop Dell Latitude 5440 "
                "và 30 Bản quyền Microsoft 365 Business Premium kèm Dịch vụ triển khai Microsoft 365. "
                "Thời hạn dự kiến cuối tháng (trong 15 ngày). Hiện bên mình chưa chốt ngân sách và cũng chưa rõ sếp nào sẽ ký duyệt."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-005",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Ngân hàng TMCP Phương Đông - CN Hà Nội",
            "contact_name": "anh Hải - Phòng Mua sắm (hai.pv@ocb-demo.vn)",
            "approver": "Ông Phạm Minh Đức - Giám đốc Chi nhánh",
            "request_text": (
                "Gửi Minh An, chi nhánh cần bổ sung thiết bị theo báo giá cũ hồi quý 3 gồm: "
                "10 Laptop Dell Latitude 5440 (giá cũ 18.5 triệu/máy), 10 Màn hình Dell P2425H, "
                "10 Bộ bàn phím & chuột không dây Logitech MK295, 02 Tường lửa FortiGate 60F, "
                "và 01 Gói triển khai & cấu hình hạ tầng mạng LAN văn phòng. "
                "Ngân sách duyệt: 350 triệu đồng. Thời hạn giao trong 10 ngày. Chiết khấu đề nghị 5%. "
                "Người phê duyệt: Ông Phạm Minh Đức - Giám đốc Chi nhánh."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-006",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Công ty TNHH Kiến trúc Đông Á",
            "contact_name": "chị Trang (trang@donga-arch.vn)",
            "approver": "Ông Hoàng Gia Bảo - Giám đốc",
            "request_text": (
                "Công ty TNHH Kiến trúc Đông Á cần mua 10 Laptop Lenovo ThinkPad X1 Carbon Gen 12 cho khối thiết kế quản lý dự án. "
                "Ngân sách tối đa chỉ có 320 triệu VNĐ. Cần giao trong 7 ngày tới, chiết khấu 3%. "
                "Người phê duyệt: Ông Hoàng Gia Bảo - Giám đốc."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-007",
            "received_date": "2026-11-11",
            "channel": "Biểu mẫu Web",
            "customer_name": "Trường Quốc tế Horizon",
            "contact_name": "thầy Minh - IT (minh@horizon-edu.vn)",
            "approver": "Bà Nguyễn Thu Thủy - Hiệu trưởng",
            "request_text": (
                "Nhà trường muốn nâng cấp hệ thống Wi-Fi Aruba AP22 cho 3 tầng khu giảng đường, "
                "ngân sách khoảng 160 triệu đồng, người duyệt là Bà Nguyễn Thu Thủy - Hiệu trưởng. "
                "Chưa rõ số lượng bộ phát cụ thể và chưa xác định thời hạn triển khai chính xác."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-008",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Công ty CP Công nghệ VietLink",
            "contact_name": "anh Sơn (son.dt@vietlink.vn)",
            "approver": "Ông Đặng Hoàng Vũ - CTO",
            "request_text": (
                "VietLink cần báo giá nâng cấp phòng server:\n"
                "- 02 Máy chủ Dell PowerEdge R550\n"
                "- 02 Switch Aruba CX 6100\n"
                "- 02 Bộ lưu điện APC Smart-UPS 3000VA\n"
                "Ngân sách 320 triệu đồng, thời hạn triển khai trong 12 ngày, đề nghị chiết khấu 4%. "
                "Người phê duyệt: Ông Đặng Hoàng Vũ - CTO."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-009",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Tập đoàn Thực phẩm Sao Mai",
            "contact_name": "chị Vy (vy.nt@saomaifood.vn)",
            "approver": "Ông Lý Quốc Hưng - CIO",
            "request_text": (
                "Tập đoàn Thực phẩm Sao Mai đặt hàng triển khai chuyển đổi số:\n"
                "- 60 Bản quyền Microsoft 365 Business Premium\n"
                "- 02 Thiết bị tường lửa FortiGate 100F\n"
                "- 01 Dịch vụ triển khai & chuyển đổi dữ liệu Microsoft 365\n"
                "Ngân sách 520 triệu đồng. Thời hạn triển khai trong 14 ngày. Đề nghị chiết khấu 8%. "
                "Người phê duyệt: Ông Lý Quốc Hưng - CIO."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-010",
            "received_date": "2026-11-11",
            "channel": "Biểu mẫu Web",
            "customer_name": "Công ty TNHH Tư vấn Luật Thành Công",
            "contact_name": "anh Kiên (kien@thanhconglaw.vn)",
            "approver": "",
            "request_text": (
                "Bên công ty luật cần mua 10 Laptop Dell Latitude 5440 và 10 Màn hình Dell P2425H. "
                "Ngân sách 260 triệu VNĐ. Cần giao trong 10 ngày, chiết khấu 3%."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-011",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Công ty CP Truyền thông Ánh Dương",
            "contact_name": "chị Thảo (thao@anhduongmedia.vn)",
            "approver": "Bà Phan Ngọc Diệp - Giám đốc Điều hành",
            "request_text": (
                "Ánh Dương cần bổ sung thiết bị cho nhân sự mới:\n"
                "- 20 Màn hình Dell P2425H\n"
                "- 20 Bộ bàn phím & chuột không dây Logitech MK295\n"
                "Ngân sách 120 triệu đồng. Thời hạn giao trong 5 ngày. Chiết khấu 2%. "
                "Người phê duyệt: Bà Phan Ngọc Diệp - Giám đốc Điều hành."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
        {
            "request_id": "REQ-2026-012",
            "received_date": "2026-11-11",
            "channel": "Email",
            "customer_name": "Bệnh viện Đa khoa Tâm Đức",
            "contact_name": "anh Phúc - Trưởng phòng CNTT (phuc@tamduchospital.vn)",
            "approver": "TS.BS Lê Văn Minh - Giám đốc Bệnh viện",
            "request_text": (
                "Bệnh viện Đa khoa Tâm Đức cần mua sắm tập trung:\n"
                "- 25 Laptop Dell Latitude 5440\n"
                "- 05 Switch Aruba CX 6100\n"
                "- 01 Thiết bị tường lửa FortiGate 100F\n"
                "Ngân sách dự kiến 650 triệu VNĐ. Thời hạn bàn giao trong 12 ngày. "
                "Bệnh viện đề nghị mức chiết khấu ưu đãi 15%. Người duyệt: TS.BS Lê Văn Minh - Giám đốc Bệnh viện."
            ),
            "budget_hint": "",
            "deadline_hint": "",
            "discount_hint": "",
        },
    ]


def build_sample_workbook_bytes() -> bytes:
    """Build the multi-sheet XLSX workbook containing all 4 Minh An tables."""
    requests = get_sample_requests()
    catalog = get_default_catalog()
    policy = get_default_policy()["tiers"]
    team = get_default_sales_team()

    req_headers = [
        "Ma_Yeu_Cau", "Ngay_Tiep_Nhan", "Kenh_Tiep_Nhan",
        "Ten_Khach_Hang", "Nguoi_Lien_He", "Nguoi_Phe_Duyet", "Noi_Dung_Yeu_Cau",
    ]
    req_rows = [
        [
            r["request_id"], r["received_date"], r["channel"],
            r["customer_name"], r["contact_name"], r["approver"], r["request_text"],
        ]
        for r in requests
    ]

    cat_headers = [
        "Ma_SP", "Ten_San_Pham", "Nhom_SP", "Don_Vi", "Tu_Khoa",
        "Gia_Niem_Yet", "Gia_Cu", "Gia_Von", "Phien_Ban_Gia",
        "Ton_Kha_Dung", "Thoi_Gian_Nhap_Hang_Ngay", "Thoi_Gian_Trien_Khai_Ngay",
    ]
    cat_rows = [
        [
            p["sku"], p["name"], p["category"], p["unit"], "; ".join(p["aliases"]),
            p["current_price"], p["old_price"], p["cost_price"], p["price_version"],
            p["stock"], p["restock_days"], p["deploy_days"],
        ]
        for p in catalog
    ]

    pol_headers = [
        "Ma_Chinh_Sach", "Ten_Chinh_Sach", "Gia_Tri_Don_Toi_Thieu", "Gia_Tri_Don_Toi_Da",
        "Chiet_Khau_Toi_Da_NVKD", "Chiet_Khau_Toi_Da_TP", "Cap_Duyet", "Ghi_Chu",
    ]
    pol_rows = [
        [
            t["rule_id"], t["rule_name"], t["min_order_value"],
            t["max_order_value"] if t["max_order_value"] is not None else "",
            t["max_rep_discount"], t["max_manager_discount"], t["approver_role"], t["notes"],
        ]
        for t in policy
    ]

    team_headers = ["Ma_NV", "Ho_Ten", "Chuyen_Mon", "So_Ho_So_Dang_Xu_Ly", "Dinh_Muc_Tuan", "Email"]
    team_rows = [
        [m["rep_id"], m["name"], m["specialty"], m["active_deals"], m["weekly_capacity"], m["email"]]
        for m in team
    ]

    return build_xlsx_bytes([
        ("Yeu cau khach hang", req_headers, req_rows),
        ("San pham & Ton kho", cat_headers, cat_rows),
        ("Chinh sach chiet khau", pol_headers, pol_rows),
        ("Nhan vien Kinh doanh", team_headers, team_rows),
    ])


def _rows_to_csv_bytes(headers: List[str], rows: List[List[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    # Use UTF-8 with BOM so Microsoft Excel on macOS/Windows opens Vietnamese cleanly
    return buf.getvalue().encode("utf-8-sig")


def generate_sample_files(sample_dir: str) -> None:
    """Write ready-to-use XLSX and CSV sample files into sample_dir."""
    os.makedirs(sample_dir, exist_ok=True)

    xlsx_path = os.path.join(sample_dir, "MinhAn_DuLieu_Mau_TongHop.xlsx")
    with open(xlsx_path, "wb") as f:
        f.write(build_sample_workbook_bytes())

    requests = get_sample_requests()
    req_csv = _rows_to_csv_bytes(
        ["Ma_Yeu_Cau", "Ngay_Tiep_Nhan", "Kenh_Tiep_Nhan", "Ten_Khach_Hang", "Nguoi_Lien_He", "Nguoi_Phe_Duyet", "Noi_Dung_Yeu_Cau"],
        [[r["request_id"], r["received_date"], r["channel"], r["customer_name"], r["contact_name"], r["approver"], r["request_text"]] for r in requests],
    )
    with open(os.path.join(sample_dir, "yeu_cau_khach_hang.csv"), "wb") as f:
        f.write(req_csv)

    catalog = get_default_catalog()
    cat_csv = _rows_to_csv_bytes(
        ["Ma_SP", "Ten_San_Pham", "Nhom_SP", "Don_Vi", "Tu_Khoa", "Gia_Niem_Yet", "Gia_Cu", "Gia_Von", "Phien_Ban_Gia", "Ton_Kha_Dung", "Thoi_Gian_Nhap_Hang_Ngay", "Thoi_Gian_Trien_Khai_Ngay"],
        [[p["sku"], p["name"], p["category"], p["unit"], "; ".join(p["aliases"]), p["current_price"], p["old_price"], p["cost_price"], p["price_version"], p["stock"], p["restock_days"], p["deploy_days"]] for p in catalog],
    )
    with open(os.path.join(sample_dir, "danh_muc_san_pham_gia_ton_kho.csv"), "wb") as f:
        f.write(cat_csv)

    policy = get_default_policy()["tiers"]
    pol_csv = _rows_to_csv_bytes(
        ["Ma_Chinh_Sach", "Ten_Chinh_Sach", "Gia_Tri_Don_Toi_Thieu", "Gia_Tri_Don_Toi_Da", "Chiet_Khau_Toi_Da_NVKD", "Chiet_Khau_Toi_Da_TP", "Cap_Duyet", "Ghi_Chu"],
        [[t["rule_id"], t["rule_name"], t["min_order_value"], t["max_order_value"] or "", t["max_rep_discount"], t["max_manager_discount"], t["approver_role"], t["notes"]] for t in policy],
    )
    with open(os.path.join(sample_dir, "chinh_sach_chiet_khau.csv"), "wb") as f:
        f.write(pol_csv)
