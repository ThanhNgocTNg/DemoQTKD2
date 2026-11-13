"""Comprehensive tests for Minh An B2B Sales AI Agent."""

from __future__ import annotations

import base64
import email.parser
import io
import json
import os
import sys
import unittest
from typing import Dict, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.normalizer import detect_sheet_role
from agent.parsers import (
    build_xlsx_bytes,
    extract_google_sheets_info,
    parse_csv_bytes,
    parse_xlsx_bytes,
)
from agent.sample_data import (
    build_sample_workbook_bytes,
    get_default_catalog,
    get_default_policy,
    get_default_sales_team,
    get_sample_requests,
)
from agent.workflow_engine import process_batch
from app import MinhAnHTTPHandler, WORKSPACE


class TestParsersAndNormalizer(unittest.TestCase):
    def test_xlsx_roundtrip_multisheet_and_role_detection(self) -> None:
        wb_bytes = build_sample_workbook_bytes()
        sheets = parse_xlsx_bytes(wb_bytes)
        self.assertEqual(len(sheets), 4)
        roles = [detect_sheet_role(s) for s in sheets]
        self.assertEqual(roles, ["requests", "catalog", "policy", "sales_team"])
        self.assertEqual(len(sheets[0].rows), 12)
        self.assertEqual(len(sheets[1].rows), 14)

    def test_xlsx_sparse_columns_and_shared_strings(self) -> None:
        xlsx = build_xlsx_bytes([
            ("Test", ["ColA", "ColB", "ColC"], [["A1", "", "C1"], ["", 42, "Tiếng Việt có dấu"]])
        ])
        sheets = parse_xlsx_bytes(xlsx)
        self.assertEqual(sheets[0].rows[0]["ColA"], "A1")
        self.assertEqual(sheets[0].rows[0]["ColB"], "")
        self.assertEqual(sheets[0].rows[0]["ColC"], "C1")
        self.assertEqual(sheets[0].rows[1]["ColB"], "42")
        self.assertEqual(sheets[0].rows[1]["ColC"], "Tiếng Việt có dấu")

    def test_csv_semicolon_and_multiline(self) -> None:
        csv_text = (
            'Ma_Yeu_Cau;Ten_Khach_Hang;Noi_Dung_Yeu_Cau\n'
            'REQ-1;Công ty ABC;"Cần 5 Laptop Dell Latitude 5440\nNgân sách 150 triệu"\n'
        ).encode("utf-8-sig")
        sheets = parse_csv_bytes(csv_text, "test")
        self.assertEqual(len(sheets[0].rows), 1)
        self.assertEqual(sheets[0].rows[0]["Ten_Khach_Hang"], "Công ty ABC")
        self.assertIn("Ngân sách 150 triệu", sheets[0].rows[0]["Noi_Dung_Yeu_Cau"])

    def test_google_sheets_url_extraction(self) -> None:
        sid, gid, pub = extract_google_sheets_info(
            "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit?gid=12345#gid=12345"
        )
        self.assertEqual(sid, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "12345")
        self.assertIsNone(pub)

        sid2, gid2, pub2 = extract_google_sheets_info(
            "https://docs.google.com/spreadsheets/d/e/2PACX-1vTestPubId/pubhtml?gid=0&single=true"
        )
        self.assertIsNone(sid2)
        self.assertEqual(gid2, "0")
        self.assertEqual(pub2, "2PACX-1vTestPubId")


class TestWorkflowEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.result = process_batch(
            get_sample_requests(),
            get_default_catalog(),
            get_default_policy(),
            get_default_sales_team(),
        )
        self.by_req = {o["request_id"]: o for o in self.result["opportunities"]}

    def test_standard_complete_request_passes_without_escalation(self) -> None:
        opp = self.by_req["REQ-2026-001"]
        self.assertTrue(opp["has_complete_info"])
        self.assertEqual(len(opp["line_items"]), 3)
        self.assertEqual(opp["workflow_stage_code"], "KET_THUC_THEO_DOI")
        self.assertFalse(opp["approval_summary"]["requires_manager_approval"])
        self.assertTrue(opp["timeline_summary"]["is_feasible"])

    def test_discount_escalation_routes_to_manager(self) -> None:
        opp = self.by_req["REQ-2026-002"]
        self.assertTrue(opp["has_complete_info"])
        self.assertEqual(len(opp["line_items"]), 4)
        self.assertEqual(opp["workflow_stage_code"], "TRUONG_PHONG_DUYET")
        self.assertTrue(opp["approval_summary"]["requires_manager_approval"])

    def test_stock_shortage_and_impossible_deadline_detected(self) -> None:
        opp = self.by_req["REQ-2026-003"]
        self.assertTrue(opp["alerts"]["deadline_risk"])
        self.assertGreater(len(opp["alerts"]["stock_alerts"]), 0)
        self.assertFalse(opp["timeline_summary"]["is_feasible"])
        self.assertEqual(opp["timeline_summary"]["requested_days"], 4)
        self.assertGreater(opp["timeline_summary"]["feasible_days"], 4)

    def test_missing_budget_and_approver_still_assigned_owner(self) -> None:
        opp = self.by_req["REQ-2026-004"]
        self.assertFalse(opp["has_complete_info"])
        self.assertEqual(opp["workflow_stage_code"], "YEU_CAU_BO_SUNG")
        self.assertTrue(opp["assigned_rep"]["name"])
        self.assertIn("Chủ đề:", opp["customer_response_draft"])

    def test_old_price_warning_and_zero_omission_5_items(self) -> None:
        opp = self.by_req["REQ-2026-005"]
        self.assertEqual(len(opp["line_items"]), 5)
        self.assertGreater(len(opp["alerts"]["old_price_alerts"]), 0)
        laptop_item = next(it for it in opp["line_items"] if it["sku"] == "LAP-DELL-5440")
        self.assertEqual(laptop_item["unit_price"], 19_900_000)

    def test_over_budget_flagged_with_recommendation(self) -> None:
        opp = self.by_req["REQ-2026-006"]
        self.assertFalse(opp["pricing_summary"]["within_budget"])
        self.assertGreater(opp["pricing_summary"]["budget_diff_vnd"], 0)

    def test_unlisted_product_not_dropped(self) -> None:
        opp = self.by_req["REQ-2026-008"]
        self.assertEqual(len(opp["line_items"]), 2)
        self.assertEqual(len(opp["unmatched_items"]), 1)
        self.assertIn("APC Smart-UPS", opp["unmatched_items"][0]["raw_text"])


class _InProcessHandler(MinhAnHTTPHandler):
    """Minimal wrapper to invoke MinhAnHTTPHandler directly without OS sockets."""

    def __init__(self, method: str, path: str, body: bytes = b"") -> None:
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.1"
        self.requestline = f"{method} {path} HTTP/1.1"
        self.client_address = ("127.0.0.1", 0)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = email.parser.Parser().parsestr(
            f"Host: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
        )
        self.close_connection = True
        self._headers_buffer = []
        if method == "GET":
            self.do_GET()
        else:
            self.do_POST()

    def response_parts(self) -> Tuple[int, bytes]:
        raw = self.wfile.getvalue()
        header_end = raw.find(b"\r\n\r\n")
        head = raw[:header_end].decode("latin-1")
        status = int(head.splitlines()[0].split()[1])
        return status, raw[header_end + 4:]


class TestHttpServerEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        WORKSPACE.load_demo()

    def _get(self, path: str) -> Tuple[int, bytes]:
        return _InProcessHandler("GET", path).response_parts()

    def _post_json(self, path: str, payload: dict) -> Tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8")
        status, body = _InProcessHandler("POST", path, data).response_parts()
        return status, json.loads(body.decode("utf-8"))

    def test_homepage_and_state(self) -> None:
        status, html_bytes = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("Công ty Công nghệ Minh An", html_bytes.decode("utf-8"))

        st_status, st_bytes = self._get("/api/state")
        self.assertEqual(st_status, 200)
        st = json.loads(st_bytes.decode("utf-8"))
        self.assertTrue(st["ok"])
        self.assertEqual(len(st["state"]["opportunities"]), 12)

    def test_import_xlsx_supplement_and_manager_approval(self) -> None:
        wb_b64 = base64.b64encode(build_sample_workbook_bytes()).decode("ascii")
        status, res = self._post_json("/api/import/files", {
            "files": [{"filename": "MinhAn.xlsx", "role": "auto", "content_base64": wb_b64}],
            "replace_requests": True,
        })
        self.assertEqual(status, 200)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["import_report"]), 4)

        # Supplement REQ-2026-004 (which was missing budget & approver)
        opp4 = next(o for o in res["state"]["opportunities"] if o["request_id"] == "REQ-2026-004")
        s_status, supp_res = self._post_json("/api/opportunity/supplement", {
            "opportunity_id": opp4["opportunity_id"],
            "budget": "550 triệu",
            "approver": "Ông Trần Bình - Giám đốc",
            "deadline": "15 ngày",
        })
        self.assertEqual(s_status, 200)
        self.assertTrue(supp_res["updated_opportunity"]["has_complete_info"])
        self.assertEqual(supp_res["updated_opportunity"]["workflow_stage_code"], "KET_THUC_THEO_DOI")

        # Manager approves REQ-2026-002
        opp2 = next(o for o in supp_res["state"]["opportunities"] if o["request_id"] == "REQ-2026-002")
        self.assertEqual(opp2["workflow_stage_code"], "TRUONG_PHONG_DUYET")
        m_status, mgr_res = self._post_json("/api/opportunity/manager-decision", {
            "opportunity_id": opp2["opportunity_id"],
            "decision": "approve",
            "approved_discount": 8.0,
            "manager_note": "Đồng ý duyệt 8% cho đơn lớn.",
        })
        self.assertEqual(m_status, 200)
        self.assertEqual(mgr_res["updated_opportunity"]["workflow_stage_code"], "KET_THUC_THEO_DOI")
        self.assertEqual(mgr_res["updated_opportunity"]["pricing_summary"]["applied_discount_pct"], 8.0)

        # Evaluate single quick request
        q_status, quick_res = self._post_json("/api/evaluate-single", {
            "customer_name": "Công ty TNHH Test Nhanh",
            "request_text": "Cần mua 5 Laptop Dell Latitude 5440, ngân sách 120 triệu, giao trong 7 ngày, anh An GĐ duyệt.",
        })
        self.assertEqual(q_status, 200)
        self.assertTrue(quick_res["created_opportunity"]["has_complete_info"])

        # Verify exported XLSX is valid
        exp_status, export_bytes = self._get("/api/export/results.xlsx")
        self.assertEqual(exp_status, 200)
        parsed_export = parse_xlsx_bytes(export_bytes)
        self.assertEqual(len(parsed_export), 2)
        self.assertEqual(len(parsed_export[0].rows), 13)

    def test_invalid_google_sheets_url_returns_400(self) -> None:
        status, res = self._post_json("/api/import/google-sheets", {
            "url": "https://example.com/not-a-sheet"
        })
        self.assertEqual(status, 400)
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
