"""Minh An B2B Sales AI Agent Web Server & API."""

from __future__ import annotations

import argparse
import base64
import copy
import csv
import datetime as dt
import io
import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from agent.llm_client import refine_customer_draft_with_llm, test_llm_connection
from agent.normalizer import (
    detect_sheet_role,
    merge_inventory_sheet,
    normalize_catalog_sheet,
    normalize_policy_sheet,
    normalize_requests_sheet,
    normalize_sales_team_sheet,
)
from agent.parsers import (
    DataImportError,
    ParsedSheet,
    build_xlsx_bytes,
    fetch_google_sheets,
    parse_uploaded_file,
)
from agent.sample_data import (
    build_sample_workbook_bytes,
    generate_sample_files,
    get_default_catalog,
    get_default_policy,
    get_default_sales_team,
    get_sample_requests,
)
from agent.workflow_engine import (
    apply_manager_decision,
    build_executive_summary,
    evaluate_single_request,
    process_batch,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")


class WorkspaceState:
    """Thread-safe in-memory workspace storing Minh An's active datasets and AI Agent results."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.catalog: List[Dict[str, Any]] = get_default_catalog()
        self.policy: Dict[str, Any] = get_default_policy()
        self.sales_team: List[Dict[str, Any]] = get_default_sales_team()
        self.requests: List[Dict[str, Any]] = get_sample_requests()
        self.opportunities: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}
        self.sales_team_load: List[Dict[str, Any]] = []
        self.source_info: Dict[str, Any] = {
            "mode": "demo",
            "label": "Bộ dữ liệu mẫu Công ty Minh An (12 yêu cầu B2B thực tế)",
            "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sheets_detected": [],
        }
        self._recompute_locked()

    def _recompute_locked(self) -> None:
        result = process_batch(self.requests, self.catalog, self.policy, self.sales_team)
        self.opportunities = result["opportunities"]
        self.summary = result["summary"]
        self.sales_team_load = result["sales_team_load"]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "catalog": copy.deepcopy(self.catalog),
                "policy": copy.deepcopy(self.policy),
                "sales_team": copy.deepcopy(self.sales_team),
                "requests": copy.deepcopy(self.requests),
                "opportunities": copy.deepcopy(self.opportunities),
                "summary": copy.deepcopy(self.summary),
                "sales_team_load": copy.deepcopy(self.sales_team_load),
                "source_info": copy.deepcopy(self.source_info),
            }

    def load_demo(self) -> Dict[str, Any]:
        with self._lock:
            self.catalog = get_default_catalog()
            self.policy = get_default_policy()
            self.sales_team = get_default_sales_team()
            self.requests = get_sample_requests()
            self._recompute_locked()
            self.source_info = {
                "mode": "demo",
                "label": "Bộ dữ liệu mẫu Công ty Minh An (12 yêu cầu B2B thực tế)",
                "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sheets_detected": [
                    {"name": "Yêu cầu khách hàng", "role": "requests", "rows": len(self.requests)},
                    {"name": "Sản phẩm & Tồn kho", "role": "catalog", "rows": len(self.catalog)},
                    {"name": "Chính sách chiết khấu", "role": "policy", "rows": len(self.policy["tiers"])},
                    {"name": "Nhân viên Kinh doanh", "role": "sales_team", "rows": len(self.sales_team)},
                ],
            }
            return self.snapshot()

    def apply_parsed_sheets(
        self,
        sheet_items: List[Tuple[ParsedSheet, Optional[str]]],
        source_mode: str,
        source_label: str,
        replace_requests: bool = True,
    ) -> Dict[str, Any]:
        """Classify and ingest uploaded ParsedSheets into active datasets and re-run workflow."""
        with self._lock:
            detected_report: List[Dict[str, Any]] = []
            incoming_requests: List[Dict[str, Any]] = []
            pending_inventories: List[ParsedSheet] = []
            updated_roles: set[str] = set()

            for sheet, forced_role in sheet_items:
                role = forced_role if forced_role and forced_role != "auto" else detect_sheet_role(sheet)
                detected_report.append({
                    "name": sheet.name,
                    "role": role,
                    "rows": len(sheet.rows),
                    "headers": sheet.headers,
                })

                if role == "catalog":
                    parsed_cat = normalize_catalog_sheet(sheet)
                    if parsed_cat:
                        self.catalog = parsed_cat
                        updated_roles.add("catalog")
                elif role == "inventory":
                    pending_inventories.append(sheet)
                    updated_roles.add("inventory")
                elif role == "policy":
                    parsed_pol = normalize_policy_sheet(sheet)
                    if parsed_pol.get("tiers"):
                        self.policy = parsed_pol
                        updated_roles.add("policy")
                elif role == "sales_team":
                    parsed_team = normalize_sales_team_sheet(sheet)
                    if parsed_team:
                        self.sales_team = parsed_team
                        updated_roles.add("sales_team")
                else:
                    reqs = normalize_requests_sheet(sheet)
                    incoming_requests.extend(reqs)
                    updated_roles.add("requests")

            # Merge any separate inventory sheets after catalog is loaded
            for inv_sheet in pending_inventories:
                self.catalog = merge_inventory_sheet(self.catalog, inv_sheet)

            if incoming_requests:
                if replace_requests:
                    self.requests = incoming_requests
                else:
                    self.requests.extend(incoming_requests)
            elif "requests" in updated_roles and not incoming_requests:
                raise DataImportError("Sheet yêu cầu khách hàng không có dòng dữ liệu hợp lệ.")

            self._recompute_locked()
            self.source_info = {
                "mode": source_mode,
                "label": source_label,
                "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sheets_detected": detected_report,
                "updated_roles": sorted(updated_roles),
            }
            return {
                "state": self.snapshot(),
                "import_report": detected_report,
                "updated_roles": sorted(updated_roles),
            }

    def add_single_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            next_num = len(self.requests) + 1
            new_req = {
                "request_id": (payload.get("request_id") or "").strip() or f"REQ-NEW-{next_num:03d}",
                "received_date": (payload.get("received_date") or "").strip() or dt.date.today().isoformat(),
                "channel": (payload.get("channel") or "").strip() or "Nhập trực tiếp trên Agent",
                "customer_name": (payload.get("customer_name") or "").strip(),
                "contact_name": (payload.get("contact_name") or "").strip(),
                "approver": (payload.get("approver") or "").strip(),
                "request_text": (payload.get("request_text") or "").strip(),
                "budget_hint": (payload.get("budget_hint") or "").strip(),
                "deadline_hint": (payload.get("deadline_hint") or "").strip(),
                "discount_hint": (payload.get("discount_hint") or "").strip(),
            }
            if not new_req["request_text"]:
                raise DataImportError("Vui lòng nhập nội dung yêu cầu khách hàng.")

            # Insert at top so user sees the new evaluation immediately
            self.requests.insert(0, new_req)
            self._recompute_locked()
            created_opp = self.opportunities[0]
            return {"state": self.snapshot(), "created_opportunity": created_opp}

    def supplement_opportunity(self, opp_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            target_idx = next(
                (i for i, o in enumerate(self.opportunities) if o["opportunity_id"] == opp_id),
                None,
            )
            if target_idx is None:
                raise DataImportError(f"Không tìm thấy hồ sơ {opp_id}.")

            req_id = self.opportunities[target_idx]["request_id"]
            req_idx = next((i for i, r in enumerate(self.requests) if r["request_id"] == req_id), None)
            if req_idx is None:
                raise DataImportError(f"Không tìm thấy yêu cầu gốc {req_id}.")

            req = self.requests[req_idx]
            extra_notes: List[str] = []
            if updates.get("budget"):
                req["budget_hint"] = str(updates["budget"]).strip()
                extra_notes.append(f"Ngân sách bổ sung: {req['budget_hint']}")
            if updates.get("approver"):
                req["approver"] = str(updates["approver"]).strip()
                extra_notes.append(f"Người phê duyệt bổ sung: {req['approver']}")
            if updates.get("deadline"):
                req["deadline_hint"] = str(updates["deadline"]).strip()
                extra_notes.append(f"Thời hạn bổ sung: {req['deadline_hint']}")
            if updates.get("additional_text"):
                extra_notes.append(str(updates["additional_text"]).strip())

            if extra_notes:
                req["request_text"] = req["request_text"].rstrip() + "\n[KH bổ sung]: " + "; ".join(extra_notes)

            self._recompute_locked()
            updated_opp = next((o for o in self.opportunities if o["request_id"] == req_id), self.opportunities[target_idx])
            return {"state": self.snapshot(), "updated_opportunity": updated_opp}

    def manager_decide(
        self,
        opp_id: str,
        decision: str,
        approved_discount: Optional[float],
        manager_note: str,
    ) -> Dict[str, Any]:
        with self._lock:
            target_idx = next(
                (i for i, o in enumerate(self.opportunities) if o["opportunity_id"] == opp_id),
                None,
            )
            if target_idx is None:
                raise DataImportError(f"Không tìm thấy hồ sơ {opp_id}.")

            updated_opp = apply_manager_decision(
                self.opportunities[target_idx],
                decision=decision,
                approved_discount=approved_discount,
                manager_note=manager_note,
            )
            self.opportunities[target_idx] = updated_opp
            self.summary = build_executive_summary(self.opportunities, self.sales_team_load)
            return {"state": self.snapshot(), "updated_opportunity": updated_opp}

    def update_knowledge_base(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if isinstance(payload.get("catalog"), list) and payload["catalog"]:
                self.catalog = payload["catalog"]
            if isinstance(payload.get("policy"), dict) and payload["policy"]:
                self.policy = payload["policy"]
            if isinstance(payload.get("sales_team"), list) and payload["sales_team"]:
                self.sales_team = payload["sales_team"]
            self._recompute_locked()
            return self.snapshot()

    def update_opportunity_draft(self, opp_id: str, new_draft: str) -> Dict[str, Any]:
        with self._lock:
            for o in self.opportunities:
                if o["opportunity_id"] == opp_id:
                    o["customer_response_draft"] = new_draft
                    return {"state": self.snapshot(), "updated_opportunity": o}
            raise DataImportError(f"Không tìm thấy hồ sơ {opp_id}.")

    def export_results_xlsx(self) -> bytes:
        with self._lock:
            opp_headers = [
                "Ma_Co_Hoi", "Ma_Yeu_Cau", "Khach_Hang", "Nguoi_Phe_Duyet", "NVKD_Phu_Trach",
                "Trang_Thai_Quy_Trinh", "Du_Thong_Tin", "Gia_Tri_Niem_Yet", "Chiet_Khau_Ap_Dung_%",
                "Gia_Tri_Sau_CK", "Ngan_Sach_KH", "Bien_Loi_Nhuan_%", "Thoi_Han_KH_Ngay",
                "Thoi_Gian_Dap_Ung_Ngay", "Dap_Ung_Tien_Do", "Tham_Quyen_Duyet",
                "Canh_Bao_Rui_Ro", "De_Xuat_Kinh_Doanh", "Hanh_Dong_Tiep_Theo",
            ]
            opp_rows = []
            item_rows = []
            for o in self.opportunities:
                ps = o["pricing_summary"]
                ts = o["timeline_summary"]
                ap = o["approval_summary"]
                al = o["alerts"]
                alerts_list = (
                    al["old_price_alerts"]
                    + al["stock_alerts"]
                    + ([f"{al['unmatched_count']} hạng mục ngoài danh mục"] if al["unmatched_count"] else [])
                )
                opp_rows.append([
                    o["opportunity_id"],
                    o["request_id"],
                    o["customer_name"],
                    o.get("approver") or "(Chưa rõ)",
                    o["assigned_rep"]["name"],
                    o["workflow_stage"],
                    "Đủ" if o["has_complete_info"] else "Thiếu: " + "; ".join(o["missing_fields"]),
                    ps["list_total"],
                    ps["applied_discount_pct"],
                    ps["net_total"],
                    ps["budget_vnd"] if ps["budget_vnd"] is not None else "",
                    ps["gross_margin_pct"],
                    ts["requested_days"] if ts["requested_days"] is not None else "",
                    ts["feasible_days"],
                    "Đáp ứng" if ts["is_feasible"] else f"Trễ {ts['gap_days']} ngày",
                    ap["status"],
                    " | ".join(alerts_list) if alerts_list else "Không",
                    " | ".join(o["recommendations"]),
                    o["next_action"],
                ])
                for it in o["line_items"]:
                    item_rows.append([
                        o["opportunity_id"],
                        o["customer_name"],
                        it["sku"],
                        it["product_name"],
                        it["quantity"],
                        it["unit_price"],
                        it["line_total"],
                        it["stock_available"],
                        it["shortage_qty"],
                        it["stock_status"],
                        it["item_feasible_days"],
                        it["old_price_warning"],
                    ])

            item_headers = [
                "Ma_Co_Hoi", "Khach_Hang", "Ma_SP", "Ten_San_Pham", "So_Luong",
                "Don_Gia_Hien_Hanh", "Thanh_Tien", "Ton_Kha_Dung", "Thieu_Hut",
                "Trang_Thai_Kho", "Thoi_Gian_Dap_Ung_Ngay", "Canh_Bao_Gia_Cu",
            ]
            return build_xlsx_bytes([
                ("Ho so co hoi", opp_headers, opp_rows),
                ("Chi tiet hang muc", item_headers, item_rows),
            ])

    def export_results_csv(self) -> bytes:
        with self._lock:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "Ma_Co_Hoi", "Ma_Yeu_Cau", "Khach_Hang", "NVKD_Phu_Trach",
                "Trang_Thai_Quy_Trinh", "Gia_Tri_Sau_CK", "Chiet_Khau_%",
                "Thoi_Han_KH_Ngay", "Thoi_Gian_Dap_Ung_Ngay", "Trang_Thai_Duyet",
                "De_Xuat_Kinh_Doanh", "Ban_Nhap_Phan_Hoi",
            ])
            for o in self.opportunities:
                writer.writerow([
                    o["opportunity_id"],
                    o["request_id"],
                    o["customer_name"],
                    o["assigned_rep"]["name"],
                    o["workflow_stage"],
                    o["pricing_summary"]["net_total"],
                    o["pricing_summary"]["applied_discount_pct"],
                    o["timeline_summary"]["requested_days"] or "",
                    o["timeline_summary"]["feasible_days"],
                    o["approval_summary"]["status"],
                    " | ".join(o["recommendations"]),
                    o["customer_response_draft"],
                ])
            return buf.getvalue().encode("utf-8-sig")


WORKSPACE = WorkspaceState()


class MinhAnHTTPHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving the UI and AI Agent REST endpoints."""

    server_version = "MinhAnSalesAgent/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console output clean and readable
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, content_type: str, data: bytes, download_name: Optional[str] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise DataImportError("Header Content-Length không hợp lệ.")
        if length <= 0:
            return {}
        if length > 30 * 1024 * 1024:
            raise DataImportError("Dung lượng dữ liệu tải lên vượt quá giới hạn 30MB.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DataImportError("Payload JSON không hợp lệ.") from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/" or path == "/index.html":
                index_path = os.path.join(STATIC_DIR, "index.html")
                with open(index_path, "rb") as f:
                    self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", f.read())
                return

            if path.startswith("/static/"):
                rel = path[len("/static/"):].lstrip("/")
                safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel))
                if not safe_path.startswith(STATIC_DIR) or not os.path.isfile(safe_path):
                    self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Không tìm thấy tệp tĩnh."})
                    return
                mime, _ = mimetypes.guess_type(safe_path)
                with open(safe_path, "rb") as f:
                    self._send_bytes(HTTPStatus.OK, mime or "application/octet-stream", f.read())
                return

            if path == "/api/state":
                self._send_json(HTTPStatus.OK, {"ok": True, "state": WORKSPACE.snapshot()})
                return

            if path == "/api/export/results.xlsx":
                xlsx_bytes = WORKSPACE.export_results_xlsx()
                self._send_bytes(
                    HTTPStatus.OK,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    xlsx_bytes,
                    download_name="MinhAn_KetQua_PhanTich_CoHoi.xlsx",
                )
                return

            if path == "/api/export/results.csv":
                csv_bytes = WORKSPACE.export_results_csv()
                self._send_bytes(
                    HTTPStatus.OK,
                    "text/csv; charset=utf-8",
                    csv_bytes,
                    download_name="MinhAn_KetQua_PhanTich_CoHoi.csv",
                )
                return

            if path == "/api/templates/workbook.xlsx":
                wb_bytes = build_sample_workbook_bytes()
                self._send_bytes(
                    HTTPStatus.OK,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    wb_bytes,
                    download_name="MinhAn_DuLieu_Mau_TongHop.xlsx",
                )
                return

            if path in (
                "/api/templates/requests.csv",
                "/api/templates/catalog.csv",
                "/api/templates/policy.csv",
            ):
                mapping = {
                    "/api/templates/requests.csv": "yeu_cau_khach_hang.csv",
                    "/api/templates/catalog.csv": "danh_muc_san_pham_gia_ton_kho.csv",
                    "/api/templates/policy.csv": "chinh_sach_chiet_khau.csv",
                }
                fname = mapping[path]
                fpath = os.path.join(SAMPLE_DIR, fname)
                if not os.path.isfile(fpath):
                    generate_sample_files(SAMPLE_DIR)
                with open(fpath, "rb") as f:
                    self._send_bytes(HTTPStatus.OK, "text/csv; charset=utf-8", f.read(), download_name=fname)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Endpoint không tồn tại."})
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()

            if path == "/api/load-demo":
                state = WORKSPACE.load_demo()
                self._send_json(HTTPStatus.OK, {"ok": True, "state": state})
                return

            if path == "/api/import/files":
                files = body.get("files") or []
                if not files:
                    raise DataImportError("Chưa chọn file CSV hoặc XLSX nào để tải lên.")
                replace_requests = body.get("replace_requests", True)
                all_sheet_items: List[Tuple[ParsedSheet, Optional[str]]] = []
                names: List[str] = []

                for fobj in files:
                    filename = (fobj.get("filename") or "upload.csv").strip()
                    role_override = fobj.get("role") or "auto"
                    b64 = fobj.get("content_base64") or ""
                    if "," in b64 and b64.startswith("data:"):
                        b64 = b64.split(",", 1)[1]
                    raw_bytes = base64.b64decode(b64)
                    sheets = parse_uploaded_file(filename, raw_bytes)
                    names.append(filename)
                    for sh in sheets:
                        # If workbook has multiple sheets, auto-detect each sheet unless single CSV
                        per_sheet_role = role_override if len(sheets) == 1 else "auto"
                        all_sheet_items.append((sh, per_sheet_role))

                res = WORKSPACE.apply_parsed_sheets(
                    all_sheet_items,
                    source_mode="file",
                    source_label=f"Tệp tải lên: {', '.join(names)}",
                    replace_requests=bool(replace_requests),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/import/google-sheets":
                links = body.get("links") or []
                # Support either single `url` string or list of {url, role}
                if body.get("url"):
                    links = [{"url": body["url"], "role": body.get("role", "auto")}]
                links = [lnk for lnk in links if (lnk.get("url") or "").strip()]
                if not links:
                    raise DataImportError("Vui lòng nhập ít nhất 1 đường dẫn Google Sheets.")

                replace_requests = body.get("replace_requests", True)
                all_sheet_items = []
                labels = []
                for lnk in links:
                    url = lnk["url"].strip()
                    role_override = lnk.get("role") or "auto"
                    sheets, fmt = fetch_google_sheets(url)
                    labels.append(f"Google Sheets ({fmt.upper()})")
                    for sh in sheets:
                        per_sheet_role = role_override if len(sheets) == 1 else "auto"
                        all_sheet_items.append((sh, per_sheet_role))

                res = WORKSPACE.apply_parsed_sheets(
                    all_sheet_items,
                    source_mode="google_sheets",
                    source_label=" + ".join(labels),
                    replace_requests=bool(replace_requests),
                )
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/evaluate-single":
                res = WORKSPACE.add_single_request(body)
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/opportunity/supplement":
                opp_id = body.get("opportunity_id", "")
                res = WORKSPACE.supplement_opportunity(opp_id, body)
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/opportunity/manager-decision":
                opp_id = body.get("opportunity_id", "")
                decision = body.get("decision", "approve")
                approved_disc = body.get("approved_discount")
                note = body.get("manager_note", "")
                res = WORKSPACE.manager_decide(opp_id, decision, approved_disc, note)
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/opportunity/refine-draft":
                opp_id = body.get("opportunity_id", "")
                llm_config = body.get("llm_config") or {}
                snap = WORKSPACE.snapshot()
                opp = next((o for o in snap["opportunities"] if o["opportunity_id"] == opp_id), None)
                if not opp:
                    raise DataImportError(f"Không tìm thấy hồ sơ {opp_id}.")
                refined = refine_customer_draft_with_llm(opp, llm_config)
                if not refined:
                    raise DataImportError("Vui lòng cấu hình API Key trong phần Cấu hình AI trước khi dùng tính năng viết lại bằng LLM.")
                res = WORKSPACE.update_opportunity_draft(opp_id, refined)
                self._send_json(HTTPStatus.OK, {"ok": True, **res})
                return

            if path == "/api/knowledge/update":
                state = WORKSPACE.update_knowledge_base(body)
                self._send_json(HTTPStatus.OK, {"ok": True, "state": state})
                return

            if path == "/api/llm/test":
                result = test_llm_connection(
                    provider=body.get("provider", "gemini"),
                    api_key=body.get("api_key", ""),
                    model=body.get("model", ""),
                    base_url=body.get("base_url", ""),
                )
                self._send_json(HTTPStatus.OK, result)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "API endpoint không tồn tại."})
        except DataImportError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"Lỗi xử lý hệ thống: {exc}"})


def start_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = False) -> None:
    """Ensure sample files exist and start the HTTP server."""
    generate_sample_files(SAMPLE_DIR)

    chosen_port = port
    httpd: Optional[ThreadingHTTPServer] = None
    for candidate_port in [port, 8081, 8088, 8888, 0]:
        try:
            httpd = ThreadingHTTPServer((host, candidate_port), MinhAnHTTPHandler)
            chosen_port = httpd.server_address[1]
            break
        except OSError:
            continue

    if httpd is None:
        raise RuntimeError("Không thể mở cổng HTTP trên máy.")

    url = f"http://{host}:{chosen_port}"
    print("=" * 64)
    print("  MINH AN B2B SALES AI AGENT ĐÃ SẴN SÀNG!")
    print(f"  Mở trình duyệt tại: {url}")
    print("  Nhấn Ctrl+C để dừng máy chủ.")
    print("=" * 64)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng máy chủ Minh An AI Agent...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minh An B2B Sales AI Agent Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open", action="store_true", help="Tự động mở trình duyệt")
    args = parser.parse_args()
    start_server(host=args.host, port=args.port, open_browser=args.open)

