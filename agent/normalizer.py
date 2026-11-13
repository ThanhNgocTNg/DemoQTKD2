"""Vietnamese/English text normalization, sheet role detection, and column mapping."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from agent.parsers import ParsedSheet


def strip_accents(text: str) -> str:
    """Remove Vietnamese diacritics and normalize đ/Đ."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_key(text: str) -> str:
    """Normalize a header or token into lowercase ASCII snake-like form."""
    cleaned = strip_accents(text).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return cleaned.strip("_")


def parse_number(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Parse flexible integer/float string such as '15', '1,200.5', '15.000'."""
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return default

    low = strip_accents(text).lower()
    if any(tok in low for tok in ("khong gioi han", "unlimited", "vo han")):
        return 999999.0

    # Strip trailing unit words
    num_match = re.search(r"-?\d[\d.,]*", text)
    if not num_match:
        return default
    raw = num_match.group(0)

    # Heuristic for Vietnamese thousand separators (e.g., 19.900.000 or 19,900,000)
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+", raw):
        raw = raw.replace(",", "")
    elif "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        # Single comma: decimal if <= 2 trailing digits, else thousand separator
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")

    try:
        return float(raw)
    except ValueError:
        return default


def parse_money_vnd(value: Any) -> Optional[int]:
    """Parse VND monetary amount supporting 'triệu', 'tỷ', 'tr', 'k', or raw integers."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(value))

    text = str(value).strip()
    if not text:
        return None
    low = strip_accents(text).lower()
    if any(neg in low for neg in ("chua co", "chua ro", "chua chot", "khong co", "n/a", "chua xac dinh")):
        return None

    m = re.search(r"(\d[\d.,]*)\s*(ty|t|trieu|tr|trieu dong|nghin|ngan|k|m|b)?", low)
    if not m:
        return None

    base = parse_number(m.group(1))
    if base is None:
        return None
    unit = m.group(2) or ""

    if unit in ("ty", "b"):
        return int(round(base * 1_000_000_000))
    if unit in ("trieu", "tr", "trieu dong", "m"):
        return int(round(base * 1_000_000))
    if unit in ("nghin", "ngan", "k"):
        return int(round(base * 1_000))

    # Handle case like '450tr' where unit matched via 't' or omitted
    if "ty" in low:
        return int(round(base * 1_000_000_000))
    if "trieu" in low or re.search(r"\d\s*tr\b", low):
        return int(round(base * 1_000_000))
    if base < 1000 and ("vnd" not in low and "d" not in low):
        # Likely millions shorthand if explicitly in a budget column like "500"
        return int(round(base * 1_000_000)) if base <= 500 else int(round(base))
    return int(round(base))


def parse_percent(value: Any) -> Optional[float]:
    """Parse percentage string like '8%', '8.5', '0.08' (only if <=1 with % cue missing? No: keep safe)."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        val = float(value)
        # Excel percentage stored as decimal 0.08 -> convert if strictly < 1 and > 0? Wait: 0.5% is rare vs 0.08
        return round(val * 100, 2) if 0 < val < 1 else round(val, 2)
    text = str(value).strip()
    if not text:
        return None
    has_pct = "%" in text
    num = parse_number(text)
    if num is None:
        return None
    if not has_pct and 0 < num < 1:
        return round(num * 100, 2)
    return round(num, 2)


# Synonyms for automatic column mapping across Vietnamese and English sheets
_COLUMN_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "requests": {
        "request_id": ["ma_yeu_cau", "ma_yc", "request_id", "req_id", "id", "ma_ho_so", "stt"],
        "received_date": ["ngay_tiep_nhan", "ngay_nhan", "ngay_gui", "received_date", "date", "ngay", "created_at"],
        "channel": ["kenh_tiep_nhan", "kenh", "nguon", "channel", "source"],
        "customer_name": ["ten_khach_hang", "khach_hang", "cong_ty", "doanh_nghiep", "customer", "company", "client"],
        "contact_name": ["nguoi_lien_he", "lien_he", "contact", "contact_name", "email_kh", "email"],
        "approver": ["nguoi_phe_duyet", "nguoi_duyet", "approver", "decision_maker"],
        "request_text": [
            "noi_dung_yeu_cau", "yeu_cau_khach_hang", "yeu_cau", "noi_dung", "mo_ta",
            "request_text", "description", "content", "email_content", "chi_tiet_yeu_cau",
        ],
        "budget_hint": ["ngan_sach", "ngan_sach_tong", "budget", "du_kien_ngan_sach"],
        "deadline_hint": ["thoi_han", "thoi_han_trien_khai", "deadline", "han_giao", "ngay_can_hang"],
        "discount_hint": ["chiet_khau", "de_nghi_chiet_khau", "discount", "requested_discount"],
    },
    "catalog": {
        "sku": ["ma_sp", "ma_san_pham", "sku", "product_id", "ma_hang", "code"],
        "name": ["ten_sp", "ten_san_pham", "san_pham", "product_name", "name", "hang_muc"],
        "category": ["nhom_sp", "nhom_san_pham", "danh_muc", "loai", "category", "type"],
        "unit": ["don_vi", "dvt", "unit"],
        "aliases": ["tu_khoa", "alias", "aliases", "keywords", "ten_goi_khac"],
        "current_price": ["gia_niem_yet", "don_gia", "gia_hien_hanh", "gia_ban", "gia", "price", "current_price", "unit_price"],
        "old_price": ["gia_cu", "old_price", "gia_truoc_day"],
        "cost_price": ["gia_von", "cost", "cost_price"],
        "price_version": ["phien_ban_gia", "bang_gia", "price_version", "ngay_hieu_luc", "effective_date"],
        "stock": ["ton_kha_dung", "ton_kho", "so_luong_ton", "stock", "available_stock", "inventory"],
        "restock_days": ["thoi_gian_nhap_hang", "nhap_hang_ngay", "lead_time_nhap", "restock_days", "procurement_days"],
        "deploy_days": ["thoi_gian_trien_khai", "trien_khai_ngay", "thoi_gian_giao", "deploy_days", "deployment_days", "lead_time"],
    },
    "policy": {
        "rule_id": ["ma_chinh_sach", "ma_rule", "rule_id", "id"],
        "rule_name": ["ten_chinh_sach", "chinh_sach", "muc", "rule_name", "policy_name", "dieu_kien"],
        "min_order_value": ["gia_tri_don_toi_thieu", "don_hang_tu", "min_value", "tu_gia_tri"],
        "max_order_value": ["gia_tri_don_toi_da", "don_hang_den", "max_value", "den_gia_tri"],
        "max_rep_discount": ["chiet_khau_toi_da_nvkd", "nvkd_toi_da", "chiet_khau_nvkd", "max_rep_discount", "rep_limit"],
        "max_manager_discount": ["chiet_khau_toi_da_tp", "tp_toi_da", "chiet_khau_truong_phong", "max_manager_discount", "manager_limit"],
        "approver_role": ["nguoi_duyet", "cap_duyet", "tham_quyen", "approver_role", "escalation_to"],
        "notes": ["ghi_chu", "mo_ta", "quy_dinh", "notes", "description"],
    },
    "sales_team": {
        "rep_id": ["ma_nv", "ma_nvkd", "rep_id", "id"],
        "name": ["ho_ten", "ten_nv", "ten_nvkd", "nhan_vien", "name", "sales_rep"],
        "specialty": ["chuyen_mon", "nhom_phu_trach", "specialty", "focus"],
        "active_deals": ["so_ho_so_dang_xu_ly", "dang_phu_trach", "active_deals", "current_load"],
        "weekly_capacity": ["dinh_muc_tuan", "cong_suat", "capacity", "weekly_capacity"],
        "email": ["email", "mail"],
    },
}


def find_matching_column(headers: List[str], candidates: List[str]) -> Optional[str]:
    """Match a sheet header against candidate aliases via exact then substring comparison."""
    norm_headers = [(h, normalize_key(h)) for h in headers]
    norm_candidates = [normalize_key(c) for c in candidates]

    for cand in norm_candidates:
        for orig, norm in norm_headers:
            if norm == cand:
                return orig

    for cand in norm_candidates:
        if len(cand) < 4:
            continue
        for orig, norm in norm_headers:
            if cand in norm or norm in cand:
                return orig
    return None


def map_sheet_columns(headers: List[str], role: str) -> Dict[str, Optional[str]]:
    """Produce canonical-field -> actual-column-name mapping for a given role."""
    alias_spec = _COLUMN_ALIASES.get(role, {})
    return {
        field: find_matching_column(headers, aliases)
        for field, aliases in alias_spec.items()
    }


def detect_sheet_role(sheet: ParsedSheet) -> str:
    """Classify a ParsedSheet into requests, catalog, inventory, policy, or sales_team."""
    name_norm = normalize_key(sheet.name)
    headers_norm = [normalize_key(h) for h in sheet.headers]
    joined = " ".join(headers_norm)

    # Check sheet name strong signals first
    if any(k in name_norm for k in ("yeu_cau", "request", "khach_hang", "co_hoi", "inbox")):
        if any(k in joined for k in ("noi_dung", "yeu_cau", "request", "mo_ta", "khach_hang")):
            return "requests"
    if any(k in name_norm for k in ("chinh_sach", "chiet_khau", "policy", "duyet", "approval")):
        return "policy"
    if any(k in name_norm for k in ("nhan_vien", "nvkd", "sales_team", "sales_rep", "doi_ngu")):
        return "sales_team"
    if any(k in name_norm for k in ("ton_kho", "inventory", "ton_kha_dung", "trien_khai")):
        # Could be combined catalog+inventory or dedicated inventory sheet
        if "gia" in joined or "price" in joined:
            return "catalog"
        return "inventory"
    if any(k in name_norm for k in ("san_pham", "danh_muc", "bang_gia", "catalog", "product")):
        return "catalog"

    # Score header matches across roles
    scores: Dict[str, int] = {}
    for role in ("requests", "catalog", "policy", "sales_team"):
        mapping = map_sheet_columns(sheet.headers, role)
        scores[role] = sum(1 for v in mapping.values() if v is not None)

    # Boost requests if a free-text request column exists
    req_map = map_sheet_columns(sheet.headers, "requests")
    if req_map.get("request_text"):
        scores["requests"] += 3

    # Distinguish pure inventory sheet from full catalog
    cat_map = map_sheet_columns(sheet.headers, "catalog")
    if cat_map.get("sku") and cat_map.get("stock") and not cat_map.get("current_price"):
        return "inventory"

    best_role = max(scores, key=lambda r: scores[r])
    if scores[best_role] == 0:
        return "requests"
    return best_role


def normalize_requests_sheet(sheet: ParsedSheet, column_override: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Convert a requests ParsedSheet into normalized request dicts."""
    mapping = map_sheet_columns(sheet.headers, "requests")
    if column_override:
        for k, v in column_override.items():
            if v:
                mapping[k] = v

    results: List[Dict[str, Any]] = []
    for idx, row in enumerate(sheet.rows, start=1):
        req_id = row.get(mapping.get("request_id") or "", "").strip() or f"REQ-{idx:03d}"
        req_text = row.get(mapping.get("request_text") or "", "").strip()

        # Fallback: if no explicit request_text column was mapped, join longest descriptive columns
        if not req_text:
            candidate_texts = [
                f"{col}: {val}"
                for col, val in row.items()
                if val and col not in {mapping.get("request_id"), mapping.get("received_date")}
            ]
            req_text = " | ".join(candidate_texts)

        if not req_text and not row.get(mapping.get("customer_name") or "", ""):
            continue

        results.append({
            "request_id": req_id,
            "received_date": row.get(mapping.get("received_date") or "", "").strip(),
            "channel": row.get(mapping.get("channel") or "", "").strip() or "Email / Biểu mẫu",
            "customer_name": row.get(mapping.get("customer_name") or "", "").strip(),
            "contact_name": row.get(mapping.get("contact_name") or "", "").strip(),
            "approver": row.get(mapping.get("approver") or "", "").strip(),
            "request_text": req_text,
            "budget_hint": row.get(mapping.get("budget_hint") or "", "").strip(),
            "deadline_hint": row.get(mapping.get("deadline_hint") or "", "").strip(),
            "discount_hint": row.get(mapping.get("discount_hint") or "", "").strip(),
            "raw_row": row,
        })
    return results


def normalize_catalog_sheet(sheet: ParsedSheet) -> List[Dict[str, Any]]:
    """Convert a catalog (+ optional stock/lead-time) ParsedSheet into normalized product dicts."""
    mapping = map_sheet_columns(sheet.headers, "catalog")
    products: List[Dict[str, Any]] = []
    for idx, row in enumerate(sheet.rows, start=1):
        name = row.get(mapping.get("name") or "", "").strip()
        sku = row.get(mapping.get("sku") or "", "").strip() or f"SKU-{idx:03d}"
        if not name and not sku:
            continue

        price = parse_money_vnd(row.get(mapping.get("current_price") or ""))
        if price is None:
            price = 0
        old_price = parse_money_vnd(row.get(mapping.get("old_price") or ""))
        cost_price = parse_money_vnd(row.get(mapping.get("cost_price") or ""))
        stock_val = parse_number(row.get(mapping.get("stock") or ""))
        restock_val = parse_number(row.get(mapping.get("restock_days") or ""))
        deploy_val = parse_number(row.get(mapping.get("deploy_days") or ""))

        aliases_raw = row.get(mapping.get("aliases") or "", "").strip()
        aliases = [a.strip() for a in re.split(r"[;|,]", aliases_raw) if a.strip()] if aliases_raw else []

        products.append({
            "sku": sku,
            "name": name or sku,
            "category": row.get(mapping.get("category") or "", "").strip() or "Thiết bị & Dịch vụ CNTT",
            "unit": row.get(mapping.get("unit") or "", "").strip() or "Bộ",
            "aliases": aliases,
            "current_price": price,
            "old_price": old_price,
            "cost_price": cost_price if cost_price is not None else int(round(price * 0.78)),
            "price_version": row.get(mapping.get("price_version") or "", "").strip() or "Bảng giá 11/2026",
            "stock": int(stock_val) if stock_val is not None else 0,
            "restock_days": int(restock_val) if restock_val is not None else 7,
            "deploy_days": int(deploy_val) if deploy_val is not None else 2,
        })
    return products


def merge_inventory_sheet(catalog: List[Dict[str, Any]], inv_sheet: ParsedSheet) -> List[Dict[str, Any]]:
    """Merge a separate inventory/lead-time sheet into the existing product catalog by SKU or name."""
    mapping = map_sheet_columns(inv_sheet.headers, "catalog")
    by_sku = {normalize_key(p["sku"]): p for p in catalog}
    by_name = {normalize_key(p["name"]): p for p in catalog}

    for row in inv_sheet.rows:
        sku_raw = row.get(mapping.get("sku") or "", "").strip()
        name_raw = row.get(mapping.get("name") or "", "").strip()
        target = by_sku.get(normalize_key(sku_raw)) or by_name.get(normalize_key(name_raw))
        if not target:
            continue
        stock_val = parse_number(row.get(mapping.get("stock") or ""))
        restock_val = parse_number(row.get(mapping.get("restock_days") or ""))
        deploy_val = parse_number(row.get(mapping.get("deploy_days") or ""))
        if stock_val is not None:
            target["stock"] = int(stock_val)
        if restock_val is not None:
            target["restock_days"] = int(restock_val)
        if deploy_val is not None:
            target["deploy_days"] = int(deploy_val)
    return catalog


def normalize_policy_sheet(sheet: ParsedSheet) -> Dict[str, Any]:
    """Extract discount & approval policy rules from a policy sheet."""
    mapping = map_sheet_columns(sheet.headers, "policy")
    tiers: List[Dict[str, Any]] = []

    for row in sheet.rows:
        rule_name = row.get(mapping.get("rule_name") or "", "").strip()
        rep_max = parse_percent(row.get(mapping.get("max_rep_discount") or ""))
        mgr_max = parse_percent(row.get(mapping.get("max_manager_discount") or ""))
        min_val = parse_money_vnd(row.get(mapping.get("min_order_value") or "")) or 0
        max_val = parse_money_vnd(row.get(mapping.get("max_order_value") or ""))
        approver_role = row.get(mapping.get("approver_role") or "", "").strip()
        notes = row.get(mapping.get("notes") or "", "").strip()

        if not any([rule_name, rep_max is not None, mgr_max is not None, notes]):
            continue

        tiers.append({
            "rule_id": row.get(mapping.get("rule_id") or "", "").strip() or f"POL-{len(tiers) + 1:02d}",
            "rule_name": rule_name or f"Hạn mức {len(tiers) + 1}",
            "min_order_value": min_val,
            "max_order_value": max_val,
            "max_rep_discount": rep_max if rep_max is not None else 5.0,
            "max_manager_discount": mgr_max if mgr_max is not None else 12.0,
            "approver_role": approver_role or "Trưởng phòng Kinh doanh",
            "notes": notes,
        })

    # Derive global defaults from parsed policy tiers
    rep_limits = [t["max_rep_discount"] for t in tiers if t.get("max_rep_discount") is not None]
    mgr_limits = [t["max_manager_discount"] for t in tiers if t.get("max_manager_discount") is not None]
    return {
        "default_rep_max_discount": min(rep_limits) if rep_limits else 5.0,
        "default_manager_max_discount": max(mgr_limits) if mgr_limits else 12.0,
        "max_rep_order_value": 1_000_000_000,
        "min_margin_percent": 10.0,
        "tiers": tiers,
    }


def normalize_sales_team_sheet(sheet: ParsedSheet) -> List[Dict[str, Any]]:
    """Extract sales representatives roster from a sheet."""
    mapping = map_sheet_columns(sheet.headers, "sales_team")
    team: List[Dict[str, Any]] = []
    for idx, row in enumerate(sheet.rows, start=1):
        name = row.get(mapping.get("name") or "", "").strip()
        if not name:
            continue
        active_deals = parse_number(row.get(mapping.get("active_deals") or ""), 0) or 0
        weekly_cap = parse_number(row.get(mapping.get("weekly_capacity") or ""), 30) or 30
        team.append({
            "rep_id": row.get(mapping.get("rep_id") or "", "").strip() or f"NVKD-{idx:02d}",
            "name": name,
            "specialty": row.get(mapping.get("specialty") or "", "").strip() or "Tổng hợp B2B",
            "active_deals": int(active_deals),
            "weekly_capacity": int(weekly_cap),
            "email": row.get(mapping.get("email") or "", "").strip(),
        })
    return team

