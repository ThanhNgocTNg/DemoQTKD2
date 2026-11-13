"""Vietnamese B2B request NLP extractor with zero-omission line-item detection."""

from __future__ import annotations

import datetime as dt
import difflib
import re
from typing import Any, Dict, List, Optional, Tuple

from agent.normalizer import normalize_key, parse_money_vnd, parse_number, parse_percent, strip_accents


_PRODUCT_TRIGGER_WORDS = (
    "laptop", "may tinh", "pc", "workstation", "man hinh", "monitor",
    "server", "may chu", "switch", "router", "firewall", "tuong lua",
    "wifi", "wi-fi", "access point", "ups", "bo luu dien",
    "microsoft", "office", "m365", "license", "ban quyen", "phan mem",
    "trien khai", "cau hinh", "cai dat", "goi trien khai", "dich vu", "lap dat",
    "bao tri", "ban phim", "chuot", "webcam", "camera",
    "nas", "luu tru", "o cung", "ssd", "ram", "cap mang", "tu rack",
)

_METADATA_SENTENCE_STARTS = (
    "ngan sach", "kinh phi", "du toan", "budget",
    "thoi han", "han giao", "can giao", "ban giao", "tien do", "deadline",
    "chiet khau", "de nghi chiet khau", "uu dai", "giam gia",
    "nguoi phe duyet", "nguoi duyet", "nguoi ky", "phe duyet",
    "chua ro", "chua chot", "chua co", "luu y", "ghi chu", "hien ben minh",
)

_NON_ITEM_CLAUSE_STARTS = _METADATA_SENTENCE_STARTS + (
    "chao minh an", "chao ban", "kinh gui", "tran trong", "lien he", "thong tin",
)


def _parse_date_flexible(date_str: str) -> Optional[dt.date]:
    if not date_str:
        return None
    cleaned = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(cleaned[:10], fmt).date()
        except ValueError:
            continue
    return None


def _mask_parentheses(text: str) -> Tuple[str, List[str]]:
    """Temporarily mask parenthetical specs like '(i5, 16GB RAM)' before clause splitting."""
    saved: List[str] = []

    def repl(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"__PAREN_{len(saved) - 1}__"

    masked = re.sub(r"\([^)]{1,80}\)", repl, text)
    return masked, saved


def _unmask_parentheses(text: str, saved: List[str]) -> str:
    for idx, orig in enumerate(saved):
        text = text.replace(f"__PAREN_{idx}__", orig)
    return text


def _split_candidate_clauses(text: str) -> List[str]:
    """Split a multi-line/prose request into granular clauses without breaking numbers or parens."""
    masked, saved = _mask_parentheses(text)
    raw_lines = re.split(r"[\r\n]+|;", masked)
    clauses: List[str] = []

    for line in raw_lines:
        # Split sentences on '.' not followed by a digit (keeps 18.5 intact while splitting '365. Thời hạn')
        sub_sentences = re.split(r"\.(?!\d)\s*", line)
        for sent in sub_sentences:
            sent = sent.strip()
            if not sent:
                continue
            sent_norm = strip_accents(sent).lower()
            # Keep metadata/timeline/discount sentences intact rather than splitting on 'và'
            if any(sent_norm.startswith(p) for p in _METADATA_SENTENCE_STARTS) or re.search(
                r"^(?:xin|de nghi|vi lay|mong muon|hien)\b", sent_norm
            ):
                cleaned = _unmask_parentheses(sent, saved)
                if cleaned:
                    clauses.append(cleaned)
                continue

            # Split enumerations like ", 02 Firewall..." or " và 5 Switch..." or " kèm 1 Gói..."
            parts = re.split(
                r"\s*(?:,|(?:\bvà\b|\bva\b|\bkèm(?:\s+theo)?\b|\bkem(?:\s+theo)?\b|\bcùng(?:\s+với)?\b|\bcung(?:\s+voi)?\b|\bcộng thêm\b|\bngoài ra\b|\bthêm\b))\s+(?=(?:[-*•]|\d{1,4}\s|[A-Za-zÀ-ỹ]))",
                sent,
                flags=re.IGNORECASE,
            )
            for p in parts:
                cleaned = re.sub(r"^\s*(?:[-*•+]|\d+[.)])\s*", "", p).strip()
                cleaned = _unmask_parentheses(cleaned, saved)
                if cleaned:
                    clauses.append(cleaned)

    return clauses


def _tokenize_norm(text: str) -> List[str]:
    norm = strip_accents(text).lower()
    norm = re.sub(r"[^a-z0-9]+", " ", norm)
    stop = {"cua", "cho", "va", "voi", "can", "mua", "bao", "gia", "ben", "anh", "chi", "cong", "ty", "minh", "an", "goi", "cai", "chiec", "bo", "thiet", "bi"}
    return [tok for tok in norm.split() if len(tok) >= 2 and tok not in stop]


def _score_product_match(clause: str, product: Dict[str, Any]) -> float:
    """Compute semantic & fuzzy match confidence [0..1] between a clause and a catalog product."""
    clause_norm = strip_accents(clause).lower()
    sku_norm = strip_accents(product["sku"]).lower()

    # Direct SKU match
    if sku_norm and re.search(rf"\b{re.escape(sku_norm)}\b", clause_norm):
        return 0.99

    clause_tokens = set(_tokenize_norm(clause))
    if not clause_tokens:
        return 0.0

    is_service_clause = any(w in clause_norm for w in ("dich vu", "trien khai", "cai dat", "cau hinh", "migration"))
    is_service_prod = "dich vu" in strip_accents(product.get("category", "")).lower()

    best_score = 0.0
    candidates = [product["name"]] + list(product.get("aliases") or [])

    for cand in candidates:
        cand_norm = strip_accents(cand).lower()
        if cand_norm in clause_norm and len(cand_norm) >= 5:
            score = 0.95
            if is_service_clause and not is_service_prod and not any(w in clause_norm for w in ("ban quyen", "license")):
                score = 0.72
            best_score = max(best_score, score)
            continue

        cand_tokens = set(_tokenize_norm(cand))
        if not cand_tokens:
            continue

        overlap = len(clause_tokens & cand_tokens)
        if overlap == 0:
            continue

        # Recall on catalog product name tokens + Jaccard blend
        recall = overlap / len(cand_tokens)
        precision = overlap / len(clause_tokens)
        token_score = 0.7 * recall + 0.3 * precision

        # Bonus for matching model numbers / codes (e.g., 5440, 60f, dl380, p2425h, 9200, 365)
        model_tokens = [t for t in cand_tokens if any(ch.isdigit() for ch in t)]
        if model_tokens:
            matched_models = sum(1 for mt in model_tokens if mt in clause_tokens or mt in clause_norm)
            if matched_models == len(model_tokens):
                token_score += 0.2
            elif matched_models == 0 and len(model_tokens) >= 1:
                # Penalize mismatched model number (e.g. FortiGate 60F vs FortiGate 100F)
                clause_nums = {t for t in clause_tokens if any(ch.isdigit() for ch in t)}
                if clause_nums:
                    token_score *= 0.45

        seq_ratio = difflib.SequenceMatcher(None, cand_norm, clause_norm).ratio()
        combined = min(0.98, max(token_score, seq_ratio * 0.85))
        if is_service_clause and is_service_prod:
            combined = min(0.98, combined + 0.12)
        elif is_service_clause and not is_service_prod and not any(w in clause_norm for w in ("ban quyen", "license")):
            combined *= 0.78
        best_score = max(best_score, combined)

    return round(best_score, 3)


def _extract_quantity_from_clause(clause: str) -> Tuple[Optional[int], bool]:
    """Extract requested quantity from a product clause; returns (qty, was_explicit)."""
    # Strip parenthetical specs so '(16GB RAM)' or '(gen 11)' doesn't confuse quantity
    no_parens = re.sub(r"\([^)]*\)", " ", clause)
    # Strip quoted price fragments like 'giá 18.5 triệu/máy'
    no_parens = re.sub(
        r"(?:gia|bao gia|don gia)[^\d]{0,15}\d[\d.,]*\s*(?:trieu|tr|nghin|k|vnd)?",
        " ",
        no_parens,
        flags=re.IGNORECASE,
    )
    norm_low = strip_accents(no_parens).lower()

    # Ignore explicit ambiguity phrases like "chưa rõ số lượng"
    if re.search(r"chua\s+(?:ro|biet|xac dinh|chot)\s+so\s+luong", norm_low):
        return None, False

    # 1) Leading quantity: "15 Laptop Dell...", "02 Thiết bị...", "x 5 cái"
    m_lead = re.match(
        r"^\s*(?:can|mua|dat|bao gia|them|khoang|x\s+)?\s*(\d{1,4})\s*"
        r"(?:cai|chiec|bo|may|goi|license|user|tai khoan|cuon|m|met|thiet bi)?\b",
        norm_low,
    )
    if m_lead:
        qty = int(m_lead.group(1))
        if 1 <= qty <= 5000:
            return qty, True

    # 2) Quantity inside a prose clause before a unit or product noun:
    #    e.g., "Công ty X cần mua 10 Laptop Lenovo ThinkPad X1..."
    m_mid = re.search(
        r"\b(\d{1,4})\s+(?:cai|chiec|bo|may|goi|license|user|tai khoan|thiet bi|"
        r"laptop|may tinh|man hinh|may chu|server|switch|router|tuong lua|firewall|"
        r"bo phat|bo luu dien|ban quyen|ban phim)\b",
        norm_low,
    )
    if m_mid:
        qty = int(m_mid.group(1))
        if 1 <= qty <= 5000:
            return qty, True

    # 3) Explicit "số lượng: 10" or "SL: 10" or standalone "x 10" (never matching model names like X1)
    m_sl = re.search(r"(?:\bso luong|\bsl|(?:^|\s)[x×])\s*[:=]?\s*(\d{1,4})\b", norm_low)
    if m_sl:
        qty = int(m_sl.group(1))
        if 1 <= qty <= 5000:
            return qty, True

    # 4) Quantity right after a purchase verb (e.g., "cần mua 12 sản phẩm...")
    m_verb = re.search(
        r"(?:\bcan mua|\bmuon mua|\bdat mua|\bbo sung|\bmua|\bcan|\bgom)\s+(\d{1,4})\b"
        r"(?!\s*(?:tang|nha xuong|ngay|tuan|thang|nam|trieu|ty|tr|%))",
        norm_low,
    )
    if m_verb:
        qty = int(m_verb.group(1))
        if 1 <= qty <= 5000:
            return qty, True

    # 5) Trailing quantity with unit: "Màn hình Dell P2425H: 20 chiếc" (never match money or duration units)
    m_tail = re.search(
        r"[:\-]\s*(\d{1,4})\s*(?:cai|chiec|bo|may|goi|license|user)?\b"
        r"(?!\s*(?:trieu|ty|tr|nghin|ngan|vnd|dong|ngay|tuan|thang|nam|%))",
        norm_low,
    )
    if m_tail:
        qty = int(m_tail.group(1))
        if 1 <= qty <= 5000:
            return qty, True

    # 6) Implicit singular service package: "gói triển khai...", "dịch vụ cấu hình..."
    if any(w in norm_low for w in ("goi trien khai", "dich vu", "goi cai dat", "cau hinh mang", "migration")):
        return 1, False

    return None, False


def _extract_referenced_price(clause: str) -> Optional[int]:
    """Check if the customer cited an old/expected unit price inside an item line."""
    low = strip_accents(clause).lower()
    m = re.search(r"(?:gia cu|bao gia cu|gia|don gia|tam)\s*[:=]?\s*(\d[\d.,]*\s*(?:trieu|tr|nghin|k|vnd|d))(?:\s*/|\b)", low)
    if m:
        return parse_money_vnd(m.group(1))
    return None


def _is_metadata_only_clause(clause: str, has_explicit_qty: bool) -> bool:
    """Return True when a clause describes only budget, deadline, discount, or approver."""
    low = strip_accents(clause).lower().strip()
    if any(low.startswith(prefix) for prefix in _NON_ITEM_CLAUSE_STARTS):
        return True
    has_product_cue = any(re.search(rf"\b{re.escape(w)}\b", low) for w in _PRODUCT_TRIGGER_WORDS) or bool(
        re.search(r"\b(dell|hp|hpe|lenovo|asus|cisco|fortinet|fortigate|aruba|mikrotik|apc|microsoft|logitech)\b", low)
    )
    if any(cue in low for cue in ("ngan sach", "nguoi phe duyet", "nguoi duyet", "chiet khau", "thoi han bo sung")) and not has_product_cue:
        return True
    if not has_explicit_qty:
        if any(cue in low for cue in ("chiet khau", "uu dai", "ngan sach", "nguoi phe duyet", "nguoi duyet")):
            return True
        if re.search(r"\b(?:trong vong|giao hang|kip chay|han giao|thoi han|chua xac dinh)\b", low):
            return True
    return False


def _is_product_like_clause(clause: str) -> bool:
    """Heuristic to tell if an unmatched clause looks like an intended product/service item."""
    stripped = clause.strip()
    low = strip_accents(stripped).lower()
    has_qty, explicit = _extract_quantity_from_clause(stripped)
    if _is_metadata_only_clause(stripped, explicit):
        return False

    # Introductory bullet header ending with ':' without an explicit quantity
    if stripped.endswith(":") and not explicit:
        return False

    has_product_word = any(re.search(rf"\b{re.escape(w)}\b", low) for w in _PRODUCT_TRIGGER_WORDS)
    has_brand_or_model = bool(re.search(r"\b(dell|hp|hpe|lenovo|asus|cisco|fortinet|fortigate|aruba|mikrotik|apc|microsoft|logitech|synology|ubiquiti|unifi|tp-link)\b", low))
    return (explicit and (has_product_word or has_brand_or_model or len(low.split()) >= 3)) or has_product_word or has_brand_or_model


def extract_line_items(request_text: str, catalog: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract matched catalog items and unmatched item mentions without dropping any product."""
    clauses = _split_candidate_clauses(request_text)
    matched_by_sku: Dict[str, Dict[str, Any]] = {}
    unmatched_items: List[Dict[str, Any]] = []

    for clause in clauses:
        qty, qty_explicit = _extract_quantity_from_clause(clause)
        if clause.strip().endswith(":") and not qty_explicit:
            continue
        if _is_metadata_only_clause(clause, qty_explicit):
            continue

        # Rank catalog matches
        best_prod: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for prod in catalog:
            sc = _score_product_match(clause, prod)
            if sc > best_score:
                best_score = sc
                best_prod = prod

        ref_price = _extract_referenced_price(clause)

        if best_prod is not None and best_score >= 0.48:
            sku = best_prod["sku"]
            final_qty = qty if qty is not None else 1
            # Singular service packages default to 1 unit unless text says quantity is unclear
            is_service_pkg = "dich vu" in strip_accents(best_prod.get("category", "")).lower()
            qty_ambiguous = (qty is None) and not is_service_pkg
            if sku in matched_by_sku:
                matched_by_sku[sku]["quantity"] += final_qty
                matched_by_sku[sku]["source_clauses"].append(clause)
                matched_by_sku[sku]["quantity_ambiguous"] = matched_by_sku[sku]["quantity_ambiguous"] or qty_ambiguous
            else:
                matched_by_sku[sku] = {
                    "sku": sku,
                    "product_name": best_prod["name"],
                    "category": best_prod["category"],
                    "unit": best_prod["unit"],
                    "quantity": final_qty,
                    "quantity_explicit": qty_explicit,
                    "quantity_ambiguous": qty_ambiguous,
                    "match_confidence": best_score,
                    "source_clauses": [clause],
                    "customer_referenced_price": ref_price,
                    "catalog_ref": best_prod,
                }
        elif _is_product_like_clause(clause):
            unmatched_items.append({
                "raw_text": clause,
                "quantity": qty or 1,
                "quantity_explicit": qty_explicit,
                "customer_referenced_price": ref_price,
                "reason": "Chưa tìm thấy mã sản phẩm tương ứng trong danh mục Minh An",
            })

    return list(matched_by_sku.values()), unmatched_items


def extract_budget(request_text: str, budget_hint: str = "") -> Tuple[Optional[int], bool, str]:
    """Return (budget_vnd, explicitly_missing, note)."""
    if budget_hint:
        val = parse_money_vnd(budget_hint)
        if val is not None and val > 0:
            return val, False, f"Từ cột ngân sách: {budget_hint}"

    low = strip_accents(request_text).lower()
    if re.search(r"chua (?:co|chot|ro|xac dinh)[^.\n]{0,25}ngan sach|ngan sach[^.\n]{0,20}(?:chua co|chua chot|chua ro|chua xac dinh)", low):
        return None, True, "Khách hàng cho biết chưa chốt ngân sách"

    # Search around budget cues
    patterns = [
        r"(?:ngan sach|kinh phi|du toan|budget)[^.\n;]{0,35}?(\d[\d.,]*\s*(?:ty|trieu dong|trieu|tr|m|b|vnd|d)\b(?:\s*\d+)?)",
        r"(?:tam|khoang|duoi|toi da|max)\s*(\d[\d.,]*\s*(?:ty|trieu dong|trieu|tr)\b)",
    ]
    for pat in patterns:
        m = re.search(pat, low)
        if m:
            val = parse_money_vnd(m.group(1))
            if val is not None and val >= 1_000_000:
                return val, False, m.group(0).strip()

    return None, False, ""


def extract_deadline(request_text: str, received_date_str: str = "", deadline_hint: str = "") -> Tuple[Optional[int], Optional[str], bool, str]:
    """Return (deadline_days, target_date_iso, explicitly_missing, raw_phrase)."""
    ref_date = _parse_date_flexible(received_date_str) or dt.date.today()

    combined_sources = [s for s in (deadline_hint, request_text) if s]
    for src in combined_sources:
        low = strip_accents(src).lower()
        if re.search(r"chua (?:co|chot|ro|xac dinh)[^.\n]{0,25}(?:thoi han|han giao|ngay giao|tien do)", low):
            return None, None, True, "Khách hàng chưa xác định thời hạn triển khai"

        # Relative durations: "trong 10 ngày", "3 ngày tới", "2 tuần", "1 tháng"
        m_days = re.search(r"(?:trong(?:\s+vong)?|gap(?:\s+trong)?|han|toi da|muon nhat)?\s*(\d{1,3})\s*ngay(?:\s+toi|\s+lam viec)?", low)
        if m_days:
            days = int(m_days.group(1))
            if 1 <= days <= 365:
                target = ref_date + dt.timedelta(days=days)
                return days, target.isoformat(), False, m_days.group(0).strip()

        m_weeks = re.search(r"(?:trong(?:\s+vong)?|khoang)?\s*(\d{1,2})\s*tuan", low)
        if m_weeks:
            days = int(m_weeks.group(1)) * 7
            target = ref_date + dt.timedelta(days=days)
            return days, target.isoformat(), False, m_weeks.group(0).strip()

        m_months = re.search(r"(?:trong(?:\s+vong)?|khoang)?\s*(\d{1,2})\s*thang", low)
        if m_months:
            days = int(m_months.group(1)) * 30
            target = ref_date + dt.timedelta(days=days)
            return days, target.isoformat(), False, m_months.group(0).strip()

        # Explicit date dd/mm/yyyy or dd/mm
        m_date = re.search(r"(?:truoc ngay|truoc|ngay|han|deadline|ban giao)\s*[:=]?\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", low)
        if not m_date and src == deadline_hint:
            m_date = re.search(r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", low)
        if m_date:
            raw_d = m_date.group(1).replace("-", "/")
            parts = raw_d.split("/")
            try:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2]) if len(parts) == 3 else ref_date.year
                if year < 100:
                    year += 2000
                target = dt.date(year, month, day)
                if len(parts) == 2 and target < ref_date:
                    target = dt.date(year + 1, month, day)
                delta = max(1, (target - ref_date).days)
                return delta, target.isoformat(), False, m_date.group(0).strip()
            except ValueError:
                pass

        if "trong tuan nay" in low or "cuoi tuan nay" in low:
            target = ref_date + dt.timedelta(days=5)
            return 5, target.isoformat(), False, "trong tuần này (~5 ngày)"

    return None, None, False, ""


def extract_discount(request_text: str, discount_hint: str = "") -> Tuple[float, bool]:
    """Return (requested_discount_percent, was_explicitly_requested)."""
    if discount_hint:
        val = parse_percent(discount_hint)
        if val is not None and val > 0:
            return val, True

    low = strip_accents(request_text).lower()
    patterns = [
        r"(?:chiet khau|ck|giam gia|giam|uu dai|discount|ho tro gia)[^\d\n%]{0,25}(\d+(?:[.,]\d+)?)\s*%",
        r"(\d+(?:[.,]\d+)?)\s*%\s*(?:chiet khau|ck|giam|uu dai|discount)",
    ]
    for pat in patterns:
        m = re.search(pat, low)
        if m:
            val = parse_number(m.group(1))
            if val is not None and 0 <= val <= 80:
                return round(val, 2), True

    return 0.0, False


def extract_approver(request_text: str, approver_col: str = "") -> Tuple[str, bool]:
    """Return (approver_name_or_role, explicitly_missing)."""
    if approver_col:
        low_col = strip_accents(approver_col).lower()
        if any(neg in low_col for neg in ("chua ro", "chua co", "chua xac dinh", "khong ro", "n/a", "chua biet")):
            return "", True
        return approver_col.strip(), False

    low = strip_accents(request_text).lower()
    if re.search(
        r"chua (?:ro|biet|xac dinh|chot|co)[^.\n]{0,30}(?:nguoi phe duyet|nguoi duyet|ai duyet|ai ky|sep nao|cap duyet)",
        low,
    ):
        return "", True

    # Search original text with accents preserved for proper names
    orig_patterns = [
        r"(?:người phê duyệt|người duyệt|phê duyệt bởi|trình duyệt|ký duyệt bởi|người quyết định)\s*(?:bên\s+(?:anh|chị|em|công ty|tôi)\s+là|:|-)?\s*([^\n.;,]{3,70})",
        r"(?:trình|gửi)\s+((?:anh|chị|ông|bà)\s+[A-ZÀ-Ỹ][^\n.;,]{2,55}?(?:Giám đốc|Phó GĐ|Trưởng phòng|CEO|CFO|CTO|CIO|Chủ tịch)[^\n.;,]{0,30})",
        r"((?:anh|chị|ông|bà)\s+[A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,4}\s*[-–]\s*(?:Giám đốc|Phó Giám đốc|Trưởng phòng|CEO|CFO|CTO|CIO)[^\n.;,]{0,30})",
        r"((?:anh|chị|ông|bà|sếp)\s+[A-ZÀ-Ỹ][^\n.;,]{1,40}?(?:GĐ|Giám đốc|Phó GĐ|Trưởng phòng|TP|CEO|CFO|CTO|CIO))\s+(?:phê duyệt|duyệt|ký duyệt|ký)",
    ]
    for pat in orig_patterns:
        m = re.search(pat, request_text, flags=re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" :-–.")
            cand_low = strip_accents(candidate).lower()
            if not any(neg in cand_low for neg in ("chua ro", "chua co", "khong ro")):
                return candidate, False

    return "", False


def extract_customer_name(request_text: str, customer_col: str = "") -> str:
    """Extract customer company name from column or raw request text."""
    if customer_col.strip():
        return customer_col.strip()
    patterns = [
        r"((?:Công ty|Cty|Tập đoàn|Ngân hàng|Bệnh viện|Trường|Tổng công ty)\s+(?:CP|Cổ phần|TNHH|TM|DV)?\s*[A-ZÀ-Ỹ0-9][^\n,.;:]{2,60})",
    ]
    for pat in patterns:
        m = re.search(pat, request_text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return "Khách hàng Doanh nghiệp (Chưa định danh)"


def analyze_request_text(raw_req: Dict[str, Any], catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run full NLP extraction on a single normalized customer request."""
    text = raw_req.get("request_text", "")
    customer = extract_customer_name(text, raw_req.get("customer_name", ""))
    approver, approver_explicit_missing = extract_approver(text, raw_req.get("approver", ""))
    budget, budget_explicit_missing, budget_note = extract_budget(text, raw_req.get("budget_hint", ""))
    deadline_days, target_date, deadline_explicit_missing, deadline_note = extract_deadline(
        text, raw_req.get("received_date", ""), raw_req.get("deadline_hint", "")
    )
    discount_pct, discount_explicit = extract_discount(text, raw_req.get("discount_hint", ""))
    matched_items, unmatched_items = extract_line_items(text, catalog)

    return {
        "customer_name": customer,
        "approver": approver,
        "approver_explicit_missing": approver_explicit_missing,
        "budget_vnd": budget,
        "budget_explicit_missing": budget_explicit_missing,
        "budget_note": budget_note,
        "deadline_days": deadline_days,
        "target_date": target_date,
        "deadline_explicit_missing": deadline_explicit_missing,
        "deadline_note": deadline_note,
        "requested_discount_pct": discount_pct,
        "discount_explicit": discount_explicit,
        "matched_items": matched_items,
        "unmatched_items": unmatched_items,
    }
