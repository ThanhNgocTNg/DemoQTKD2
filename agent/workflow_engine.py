"""Minh An B2B Sales AI Agent Workflow Engine matching the official flowchart."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from agent.nlp_extractor import analyze_request_text
from agent.normalizer import strip_accents


def format_vnd(amount: Optional[int]) -> str:
    """Format integer VND with dot thousand separators."""
    if amount is None:
        return "Chưa xác định"
    return f"{int(round(amount)):,}".replace(",", ".") + " đ"


def _classify_request_category(matched_items: List[Dict[str, Any]], request_text: str) -> str:
    """Classify the B2B deal category for routing & analytics."""
    if matched_items:
        cats = {item["category"] for item in matched_items}
        if len(cats) == 1:
            return next(iter(cats))
        return "Giải pháp CNTT tổng hợp"

    low = strip_accents(request_text).lower()
    if any(w in low for w in ("switch", "firewall", "wifi", "router", "mang")):
        return "Hạ tầng mạng & Bảo mật"
    if any(w in low for w in ("server", "may chu", "luu tru", "cloud", "microsoft 365")):
        return "Máy chủ & Phần mềm Cloud"
    if any(w in low for w in ("laptop", "may tinh", "man hinh", "pc")):
        return "Thiết bị đầu cuối"
    return "Thiết bị & Dịch vụ CNTT"


def _select_sales_rep(
    category: str,
    team_state: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assign one of Minh An's 6 Sales Reps by specialty match and balanced active workload."""
    cat_norm = strip_accents(category).lower()

    def rep_score(rep: Dict[str, Any]) -> Tuple[int, float, int]:
        spec_norm = strip_accents(rep.get("specialty", "")).lower()
        # Match tokens between deal category and rep specialty
        cat_tokens = set(cat_norm.split())
        spec_tokens = set(spec_norm.split())
        is_match = 1 if (cat_tokens & spec_tokens) else 0
        cap = max(1, rep.get("weekly_capacity", 30))
        load_ratio = rep.get("active_deals", 0) / cap
        # Prefer lower load ratio; tie-break by specialty match
        return (0 if load_ratio < 0.95 else 1, round(load_ratio - (0.08 * is_match), 4), rep.get("active_deals", 0))

    chosen = min(team_state, key=rep_score)
    chosen["active_deals"] = chosen.get("active_deals", 0) + 1
    return dict(chosen)


def _find_applicable_policy_tier(order_value: int, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Find matching discount & approval tier from policy table."""
    tiers = policy.get("tiers") or []
    for tier in tiers:
        min_v = tier.get("min_order_value") or 0
        max_v = tier.get("max_order_value")
        if order_value >= min_v and (max_v is None or order_value <= max_v):
            return tier
    return {
        "rule_id": "POL-DEFAULT",
        "rule_name": "Chính sách chuẩn Minh An",
        "max_rep_discount": policy.get("default_rep_max_discount", 5.0),
        "max_manager_discount": policy.get("default_manager_max_discount", 12.0),
        "approver_role": "Trưởng phòng Kinh doanh",
        "notes": "Vượt hạn mức NVKD cần Trưởng phòng Kinh doanh phê duyệt.",
    }


def _find_alternatives(short_item: Dict[str, Any], catalog: List[Dict[str, Any]], needed_qty: int) -> List[Dict[str, Any]]:
    """Suggest in-stock or lower-cost alternative SKUs in the same category."""
    alts = []
    for prod in catalog:
        if prod["sku"] == short_item["sku"]:
            continue
        if prod["category"] == short_item["category"] and prod["stock"] >= needed_qty:
            alts.append({
                "sku": prod["sku"],
                "name": prod["name"],
                "stock": prod["stock"],
                "current_price": prod["current_price"],
                "deploy_days": prod["deploy_days"],
            })
    return alts[:2]


def _build_clarification_draft(
    opp: Dict[str, Any],
    missing_fields: List[str],
    rep_name: str,
) -> str:
    """Draft polite Vietnamese B2B email asking customer to clarify missing details."""
    customer = opp["customer_name"]
    missing_bullets = "\n".join(f"  {i + 1}. {m}" for i, m in enumerate(missing_fields))

    detected_line = ""
    if opp["line_items"]:
        names = ", ".join(f"{it['quantity']} {it['unit']} {it['product_name']}" for it in opp["line_items"])
        detected_line = f"\nHiện Minh An đã ghi nhận sơ bộ nhu cầu gồm: {names}."
    if opp["unmatched_items"]:
        unm = ", ".join(it["raw_text"] for it in opp["unmatched_items"])
        detected_line += f"\nNgoài ra có hạng mục cần xác nhận thêm cấu hình: {unm}."

    return (
        f"Chủ đề: [Công ty Minh An] Xác nhận thông tin để lập báo giá cho {customer} ({opp['request_id']})\n\n"
        f"Kính gửi Quý khách hàng {customer},\n\n"
        f"Công ty Công nghệ Minh An chân thành cảm ơn Quý Công ty đã gửi yêu cầu tư vấn thiết bị & giải pháp công nghệ.{detected_line}\n\n"
        f"Để đội ngũ Kinh doanh & Vận hành kiểm tra chính xác tồn kho, giữ mức giá ưu đãi nhất và cam kết tiến độ triển khai khả thi, "
        f"Quý Công ty vui lòng bổ sung giúp Minh An một số thông tin sau:\n"
        f"{missing_bullets}\n\n"
        f"Ngay khi nhận được thông tin phản hồi, Minh An sẽ hoàn thiện Báo giá chính thức và Phương án triển khai chi tiết trong vòng 4 giờ làm việc.\n\n"
        f"Trân trọng,\n"
        f"{rep_name} - Chuyên viên Kinh doanh B2B\n"
        f"Công ty Minh An | Người theo dõi hồ sơ: {opp['opportunity_id']}"
    )


def _build_quotation_draft(opp: Dict[str, Any]) -> str:
    """Draft comprehensive Vietnamese B2B proposal & quotation email."""
    customer = opp["customer_name"]
    rep_name = opp["assigned_rep"]["name"]
    pricing = opp["pricing_summary"]
    timeline = opp["timeline_summary"]
    approval = opp["approval_summary"]

    item_lines = []
    for idx, it in enumerate(opp["line_items"], start=1):
        stock_note = "Có sẵn" if it["stock_status"] == "Đủ tồn kho" else f"Có sẵn {it['stock_available']}, đặt thêm {it['shortage_qty']} ({it['restock_days']} ngày)"
        item_lines.append(
            f"  {idx}. {it['product_name']} ({it['sku']}) | SL: {it['quantity']} {it['unit']} | "
            f"Đơn giá ({it['price_version']}): {format_vnd(it['unit_price'])} | "
            f"Thành tiền: {format_vnd(it['line_total'])} | Kho: {stock_note}"
        )
    if opp["unmatched_items"]:
        for it in opp["unmatched_items"]:
            item_lines.append(
                f"  - [Cần xác nhận cấu hình bổ sung] {it['raw_text']} (SL dự kiến: {it['quantity']}) — NVKD đang báo giá riêng từ hãng."
            )

    discount_line = (
        f"  - Chiết khấu đề xuất áp dụng: {pricing['applied_discount_pct']}% (-{format_vnd(pricing['discount_amount'])})\n"
        if pricing["applied_discount_pct"] > 0
        else "  - Chiết khấu: Theo bảng giá niêm yết hiện hành (0%)\n"
    )

    if timeline["is_feasible"]:
        timeline_msg = (
            f"Minh An cam kết hoàn tất giao hàng & triển khai trong {timeline['feasible_days']} ngày làm việc "
            f"(đáp ứng thời hạn {timeline['requested_days']} ngày của Quý Công ty)."
        )
    else:
        timeline_msg = (
            f"Do một số hạng mục cần thời gian nhập hàng & cài đặt kỹ thuật, thời gian hoàn tất toàn bộ là {timeline['feasible_days']} ngày "
            f"(chậm hơn {timeline['gap_days']} ngày so với mốc {timeline['requested_days']} ngày). "
            f"Minh An đề xuất phương án giao trước các thiết bị có sẵn ngay trong {timeline['immediate_delivery_days']} ngày để Quý Công ty kịp vận hành."
        )

    approval_note = ""
    if approval["status"] == "Chờ Trưởng phòng duyệt":
        approval_note = (
            "\n[Lưu ý nội bộ trước khi gửi KH]: Hồ sơ đang trình Trưởng phòng Kinh doanh phê duyệt mức chiết khấu/điều kiện đặc biệt. "
            "Sau khi bấm Duyệt trên hệ thống, bản nháp sẽ tự động cập nhật hiệu lực chính thức."
        )
    elif approval["status"] == "Đã duyệt":
        approval_note = f"\n(Mức chiết khấu ưu đãi {pricing['applied_discount_pct']}% đã được cấp có thẩm quyền của Minh An phê duyệt)."

    approver_greet = f"Kính gửi {opp['approver']} và Quý Công ty {customer}," if opp.get("approver") else f"Kính gửi Quý Công ty {customer},"

    return (
        f"Chủ đề: [Công ty Minh An] Báo giá & Đề xuất triển khai giải pháp CNTT - {customer} ({opp['opportunity_id']})\n\n"
        f"{approver_greet}\n\n"
        f"Công ty Minh An trân trọng gửi tới Quý Công ty phương án báo giá chi tiết theo bảng giá hiện hành ({pricing['price_version']}):\n\n"
        f"I. DANH MỤC THIẾT BỊ & DỊCH VỤ:\n"
        f"{chr(10).join(item_lines)}\n\n"
        f"II. TỔNG HỢP TÀI CHÍNH:\n"
        f"  - Tổng giá trị niêm yết: {format_vnd(pricing['list_total'])}\n"
        f"{discount_line}"
        f"  - Tổng thanh toán đề xuất (chưa VAT): {format_vnd(pricing['net_total'])}\n"
        f"{approval_note}\n\n"
        f"III. KẾ HOẠCH CUNG ỨNG & TRIỂN KHAI:\n"
        f"  {timeline_msg}\n\n"
        f"Quý Công ty vui lòng phản hồi xác nhận phương án trên để Minh An tiến hành giữ hàng tồn kho và lên lịch triển khai.\n\n"
        f"Trân trọng,\n"
        f"{rep_name} - Chuyên viên Kinh doanh B2B\n"
        f"Công ty Minh An | Mã cơ hội: {opp['opportunity_id']}"
    )


def evaluate_single_request(
    raw_req: Dict[str, Any],
    idx: int,
    catalog: List[Dict[str, Any]],
    policy: Dict[str, Any],
    team_state: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Process one customer request through the entire Minh An B2B Sales Flowchart."""
    extracted = analyze_request_text(raw_req, catalog)
    opp_id = f"OPP-MA-{idx:03d}"
    category = _classify_request_category(extracted["matched_items"], raw_req.get("request_text", ""))

    # Step 1 & 2: Tiếp nhận + Phân loại & Kiểm tra thông tin
    workflow_trace: List[Dict[str, Any]] = [
        {"node": "TIEP_NHAN", "label": "Bắt đầu: Tiếp nhận yêu cầu", "status": "completed"},
        {"node": "PHAN_LOAI_KIEM_TRA", "label": "Phân loại & Kiểm tra thông tin", "status": "completed"},
    ]

    missing_fields: List[str] = []
    if not extracted["matched_items"] and not extracted["unmatched_items"]:
        missing_fields.append("Danh sách sản phẩm/dịch vụ và số lượng cụ thể cần báo giá")
    elif any(it.get("quantity_ambiguous") for it in extracted["matched_items"]):
        ambig = ", ".join(it["product_name"] for it in extracted["matched_items"] if it.get("quantity_ambiguous"))
        missing_fields.append(f"Xác nhận lại số lượng chính xác cho: {ambig}")

    if extracted["budget_vnd"] is None:
        missing_fields.append("Ngân sách dự kiến tổng của Quý Công ty (để tối ưu cấu hình phù hợp)")
    if not extracted["approver"]:
        missing_fields.append("Thông tin Người phê duyệt / Người ra quyết định phía Quý Công ty")
    if extracted["deadline_days"] is None:
        missing_fields.append("Thời hạn mong muốn bàn giao / hoàn thành triển khai")

    has_complete_info = len(missing_fields) == 0

    # Assign an owner in ALL cases (prevents un-tracked requests when missing budget/approver!)
    assigned_rep = _select_sales_rep(category, team_state)

    # Evaluate catalog items even on incomplete requests so NVKD has full context
    evaluated_items: List[Dict[str, Any]] = []
    list_total = 0
    total_cost = 0
    max_feasible_days = 0
    immediate_days = 0
    old_price_alerts: List[str] = []
    stock_alerts: List[str] = []
    item_recommendations: List[str] = []
    price_versions = set()

    for item in extracted["matched_items"]:
        prod = item["catalog_ref"]
        qty = item["quantity"]
        unit_price = prod["current_price"]
        cost_price = prod.get("cost_price", int(round(unit_price * 0.78)))
        price_ver = prod.get("price_version", "Bảng giá hiện hành")
        price_versions.add(price_ver)

        line_total = unit_price * qty
        line_cost = cost_price * qty
        list_total += line_total
        total_cost += line_cost

        stock_avail = prod.get("stock", 0)
        shortage = max(0, qty - stock_avail)
        restock_days = prod.get("restock_days", 7) if shortage > 0 else 0
        deploy_days = prod.get("deploy_days", 2)
        item_feasible_days = restock_days + deploy_days
        max_feasible_days = max(max_feasible_days, item_feasible_days)

        if shortage == 0:
            stock_status = "Đủ tồn kho"
            immediate_days = max(immediate_days, deploy_days)
        elif stock_avail > 0:
            stock_status = "Thiếu một phần"
            immediate_days = max(immediate_days, deploy_days)
            stock_alerts.append(
                f"{prod['name']}: Cần {qty} {prod['unit']}, tồn kho hiện có {stock_avail} (thiếu {shortage}, nhập thêm {restock_days} ngày)."
            )
            alts = _find_alternatives(item, catalog, qty)
            if alts:
                alt_txt = "; ".join(f"{a['name']} (tồn {a['stock']}, giá {format_vnd(a['current_price'])})" for a in alts)
                item_recommendations.append(f"Đề xuất mã thay thế có sẵn cho {prod['name']}: {alt_txt}.")
        else:
            stock_status = "Hết tồn kho"
            stock_alerts.append(
                f"{prod['name']}: Tồn kho = 0, cần nhập hàng {restock_days} ngày + triển khai {deploy_days} ngày."
            )
            alts = _find_alternatives(item, catalog, qty)
            if alts:
                alt_txt = "; ".join(f"{a['name']} (tồn {a['stock']}, giá {format_vnd(a['current_price'])})" for a in alts)
                item_recommendations.append(f"Đề xuất mã thay thế giao ngay cho {prod['name']}: {alt_txt}.")

        # Detect old price risk (either customer cited old price or catalog flags an older price changed)
        ref_price = item.get("customer_referenced_price")
        old_catalog_price = prod.get("old_price")
        old_price_warning = ""
        if ref_price and ref_price != unit_price:
            old_price_warning = (
                f"Khách hàng dẫn giá cũ {format_vnd(ref_price)}/{prod['unit']} — Đã tự động hiệu chỉnh sang giá mới {format_vnd(unit_price)} ({price_ver})."
            )
            old_price_alerts.append(old_price_warning)
        elif old_catalog_price and old_catalog_price != unit_price:
            old_price_warning = (
                f"Lưu ý bảng giá: Giá đã cập nhật từ {format_vnd(old_catalog_price)} lên {format_vnd(unit_price)} ({price_ver}); tránh gửi nhầm báo giá cũ."
            )
            old_price_alerts.append(old_price_warning)

        evaluated_items.append({
            "sku": prod["sku"],
            "product_name": prod["name"],
            "category": prod["category"],
            "unit": prod["unit"],
            "quantity": qty,
            "match_confidence": item["match_confidence"],
            "unit_price": unit_price,
            "old_price": old_catalog_price,
            "customer_referenced_price": ref_price,
            "price_version": price_ver,
            "line_total": line_total,
            "line_cost": line_cost,
            "stock_available": stock_avail,
            "shortage_qty": shortage,
            "stock_status": stock_status,
            "restock_days": restock_days,
            "deploy_days": deploy_days,
            "item_feasible_days": item_feasible_days,
            "old_price_warning": old_price_warning,
        })

    if immediate_days == 0 and max_feasible_days > 0:
        immediate_days = max_feasible_days

    unmatched_items = extracted["unmatched_items"]
    if unmatched_items:
        item_recommendations.append(
            f"Phát hiện {len(unmatched_items)} hạng mục ngoài danh mục chuẩn ({', '.join(u['raw_text'] for u in unmatched_items)}). "
            f"Đã đánh dấu tách riêng để NVKD lấy báo giá hãng, đảm bảo không bỏ sót hạng mục của khách hàng."
        )

    # Financial & Margin calculations
    req_disc = extracted["requested_discount_pct"]
    disc_amount = int(round(list_total * req_disc / 100.0))
    net_total = max(0, list_total - disc_amount)
    margin_vnd = net_total - total_cost
    margin_pct = round((margin_vnd / net_total) * 100, 1) if net_total > 0 else 0.0

    budget_vnd = extracted["budget_vnd"]
    budget_diff = (net_total - budget_vnd) if budget_vnd is not None else None
    within_budget = (net_total <= budget_vnd) if (budget_vnd is not None and net_total > 0) else None

    if within_budget is False and budget_diff is not None:
        over_pct = round((budget_diff / budget_vnd) * 100, 1) if budget_vnd else 0
        item_recommendations.append(
            f"Tổng báo giá ({format_vnd(net_total)}) vượt ngân sách khách hàng ({format_vnd(budget_vnd)}) khoảng {format_vnd(budget_diff)} (+{over_pct}%). "
            f"Đề xuất: chia 2 giai đoạn triển khai hoặc chuyển đổi sang cấu hình tối ưu chi phí hơn."
        )

    # Timeline feasibility
    req_days = extracted["deadline_days"]
    if req_days is not None and max_feasible_days > 0:
        is_feasible = max_feasible_days <= req_days
        gap_days = max(0, max_feasible_days - req_days)
    else:
        is_feasible = True if max_feasible_days > 0 else False
        gap_days = 0

    if req_days is not None and max_feasible_days > req_days:
        item_recommendations.append(
            f"Cảnh báo thời hạn: Khách hàng yêu cầu {req_days} ngày nhưng thời gian đáp ứng thực tế là {max_feasible_days} ngày (trễ {gap_days} ngày). "
            f"Không cam kết mốc {req_days} ngày; đề xuất giao trước hạng mục có sẵn trong {immediate_days} ngày và bàn giao phần còn lại sau {max_feasible_days} ngày."
        )

    # Decision 1: Branch Không -> Yêu cầu KH làm rõ / bổ sung
    if not has_complete_info:
        workflow_trace.extend([
            {"node": "DU_THONG_TIN", "label": "Có đủ thông tin?", "status": "branch_no", "decision": "Không"},
            {"node": "YEU_CAU_BO_SUNG", "label": "Yêu cầu KH làm rõ / bổ sung", "status": "active"},
        ])
        sla_followup = (dt.date.today() + dt.timedelta(days=1)).isoformat()

        opp: Dict[str, Any] = {
            "opportunity_id": opp_id,
            "request_id": raw_req["request_id"],
            "received_date": raw_req.get("received_date") or dt.date.today().isoformat(),
            "channel": raw_req.get("channel") or "Email / Biểu mẫu",
            "customer_name": extracted["customer_name"],
            "contact_name": raw_req.get("contact_name", ""),
            "approver": extracted["approver"],
            "request_text": raw_req["request_text"],
            "category": category,
            "assigned_rep": assigned_rep,
            "has_complete_info": False,
            "missing_fields": missing_fields,
            "line_items": evaluated_items,
            "unmatched_items": unmatched_items,
            "pricing_summary": {
                "list_total": list_total,
                "requested_discount_pct": req_disc,
                "applied_discount_pct": req_disc,
                "discount_amount": disc_amount,
                "net_total": net_total,
                "estimated_cost": total_cost,
                "gross_margin_pct": margin_pct,
                "budget_vnd": budget_vnd,
                "budget_diff_vnd": budget_diff,
                "within_budget": within_budget,
                "price_version": ", ".join(sorted(price_versions)) or "Bảng giá hiện hành",
            },
            "timeline_summary": {
                "requested_days": req_days,
                "target_date": extracted["target_date"],
                "deadline_note": extracted["deadline_note"],
                "feasible_days": max_feasible_days,
                "immediate_delivery_days": immediate_days,
                "is_feasible": is_feasible,
                "gap_days": gap_days,
            },
            "approval_summary": {
                "requires_manager_approval": False,
                "escalation_level": "Chưa xét (Chờ đủ thông tin)",
                "reasons": [],
                "status": "Chờ KH bổ sung",
                "policy_rule": None,
                "recommended_max_discount": None,
            },
            "alerts": {
                "old_price_alerts": old_price_alerts,
                "stock_alerts": stock_alerts,
                "unmatched_count": len(unmatched_items),
                "deadline_risk": (req_days is not None and max_feasible_days > req_days),
                "missing_info_risk": True,
            },
            "recommendations": [
                f"Đã gán người theo dõi bắt buộc: {assigned_rep['name']} ({assigned_rep['rep_id']}) với lịch nhắc SLA ngày {sla_followup} để tránh hồ sơ bị chuyển qua lại mất dấu.",
                f"Thiếu {len(missing_fields)} thông tin trọng yếu: {'; '.join(missing_fields)}. Gửi ngay bản nháp làm rõ cho khách hàng trước khi lên báo giá chính thức.",
            ] + item_recommendations,
            "workflow_stage": "Yêu cầu KH làm rõ / bổ sung",
            "workflow_stage_code": "YEU_CAU_BO_SUNG",
            "workflow_trace": workflow_trace,
            "next_action": f"Gửi email yêu cầu bổ sung thông tin & theo dõi phản hồi trước {sla_followup}",
            "followup_date": sla_followup,
            "priority": "Cần theo dõi (Thiếu thông tin)",
            "manager_decision": None,
        }
        opp["customer_response_draft"] = _build_clarification_draft(opp, missing_fields, assigned_rep["name"])
        return opp

    # Decision 1: Branch Có -> Tạo Hồ sơ Cơ hội -> Thẩm định tồn kho & giá -> Lập Báo giá
    workflow_trace.extend([
        {"node": "DU_THONG_TIN", "label": "Có đủ thông tin?", "status": "branch_yes", "decision": "Có"},
        {"node": "TAO_HO_SO_CO_HOI", "label": "Tạo Hồ sơ Cơ hội & Gán người phụ trách", "status": "completed"},
        {"node": "THAM_DINH_TON_KHO_GIA", "label": "Thẩm định tồn kho & giá (NVKD & Vận hành)", "status": "completed"},
        {"node": "LAP_BAO_GIA_DE_XUAT", "label": "Lập Báo giá & Dự thảo đề xuất", "status": "completed"},
    ])

    # Decision 2: Có vượt thẩm quyền / Cần chiết khấu đặc biệt?
    tier = _find_applicable_policy_tier(list_total, policy)
    rep_max_disc = tier.get("max_rep_discount", policy.get("default_rep_max_discount", 5.0))
    mgr_max_disc = tier.get("max_manager_discount", policy.get("default_manager_max_discount", 12.0))
    max_rep_order = policy.get("max_rep_order_value", 1_000_000_000)
    min_margin = policy.get("min_margin_percent", 10.0)

    escalation_reasons: List[str] = []
    if req_disc > rep_max_disc:
        escalation_reasons.append(
            f"Đề nghị chiết khấu {req_disc}% vượt hạn mức của NVKD ({rep_max_disc}% theo {tier['rule_name']})."
        )
    if net_total > max_rep_order:
        escalation_reasons.append(
            f"Giá trị đơn hàng {format_vnd(net_total)} vượt ngưỡng phê duyệt trực tiếp của NVKD ({format_vnd(max_rep_order)})."
        )
    if margin_pct < min_margin and net_total > 0:
        escalation_reasons.append(
            f"Biên lợi nhuận gộp dự kiến còn {margin_pct}% (thấp hơn ngưỡng an toàn {min_margin}%)."
        )
    if unmatched_items:
        escalation_reasons.append(
            f"Có {len(unmatched_items)} hạng mục ngoài danh mục cần định giá bổ sung."
        )

    requires_escalation = len(escalation_reasons) > 0
    if req_disc > mgr_max_disc:
        escalation_level = "Trưởng phòng KD -> Trình Ban Giám đốc"
    elif requires_escalation:
        escalation_level = tier.get("approver_role") or "Trưởng phòng Kinh doanh"
    else:
        escalation_level = "Trong thẩm quyền NVKD"

    # Compute recommended safe discount for Manager/Rep decision
    safe_margin_disc = 0.0
    if list_total > 0 and total_cost > 0:
        # Target at least min_margin % gross margin: (net - cost)/net >= min_margin/100
        min_allowed_net = total_cost / (1.0 - (min_margin / 100.0))
        if list_total > min_allowed_net:
            safe_margin_disc = round(((list_total - min_allowed_net) / list_total) * 100, 1)
    recommended_max_disc = min(req_disc, max(rep_max_disc, min(mgr_max_disc, safe_margin_disc)))

    business_recs: List[str] = []
    if req_disc > mgr_max_disc:
        business_recs.append(
            f"Chiết khấu đề nghị {req_disc}% vượt trần Trưởng phòng ({mgr_max_disc}%), khiến biên lợi nhuận còn {margin_pct}%. "
            f"Đề xuất phương án đàm phán: Giảm chiết khấu tiền mặt về tối đa {recommended_max_disc}% và tặng kèm gói hỗ trợ kỹ thuật onsite 12 tháng."
        )
    elif req_disc > rep_max_disc:
        business_recs.append(
            f"Chuyển Trưởng phòng Kinh doanh duyệt mức chiết khấu {req_disc}% (trong trần duyệt {mgr_max_disc}%). "
            f"Biên lợi nhuận gộp sau chiết khấu đạt {margin_pct}%."
        )
    else:
        business_recs.append(
            f"Mức chiết khấu {req_disc}% nằm trong thẩm quyền của NVKD (tối đa {rep_max_disc}%), biên lợi nhuận đạt {margin_pct}% — có thể phát hành báo giá ngay."
        )

    if old_price_alerts:
        business_recs.append(
            "Đã kiểm soát rủi ro dùng giá cũ: Toàn bộ đơn giá áp dụng theo bảng giá hiện hành mới nhất."
        )
    business_recs.extend(item_recommendations)

    if requires_escalation:
        workflow_trace.extend([
            {"node": "VUOT_THAM_QUYEN", "label": "Có vượt thẩm quyền / CK đặc biệt?", "status": "branch_yes", "decision": "Có"},
            {"node": "TRUONG_PHONG_DUYET", "label": "Trưởng phòng duyệt", "status": "active"},
        ])
        stage_label = "Chờ Trưởng phòng duyệt"
        stage_code = "TRUONG_PHONG_DUYET"
        next_action = f"Trình {escalation_level} phê duyệt trước khi gửi báo giá chính thức"
        approval_status = "Chờ Trưởng phòng duyệt"
    else:
        workflow_trace.extend([
            {"node": "VUOT_THAM_QUYEN", "label": "Có vượt thẩm quyền / CK đặc biệt?", "status": "branch_no", "decision": "Không"},
            {"node": "KET_THUC_THEO_DOI", "label": "Kết thúc: Cập nhật & Theo dõi", "status": "completed"},
        ])
        stage_label = "Sẵn sàng gửi báo giá & Theo dõi"
        stage_code = "KET_THUC_THEO_DOI"
        next_action = "Gửi bản nháp báo giá cho khách hàng & theo dõi chốt hợp đồng trong 3 ngày"
        approval_status = "Đạt chuẩn (Trong thẩm quyền)"

    priority = "Cao" if (net_total >= 400_000_000 or (req_days is not None and req_days <= 7)) else ("Trung bình" if net_total >= 150_000_000 else "Tiêu chuẩn")
    followup_date = (dt.date.today() + dt.timedelta(days=2 if requires_escalation else 3)).isoformat()

    opp = {
        "opportunity_id": opp_id,
        "request_id": raw_req["request_id"],
        "received_date": raw_req.get("received_date") or dt.date.today().isoformat(),
        "channel": raw_req.get("channel") or "Email / Biểu mẫu",
        "customer_name": extracted["customer_name"],
        "contact_name": raw_req.get("contact_name", ""),
        "approver": extracted["approver"],
        "request_text": raw_req["request_text"],
        "category": category,
        "assigned_rep": assigned_rep,
        "has_complete_info": True,
        "missing_fields": [],
        "line_items": evaluated_items,
        "unmatched_items": unmatched_items,
        "pricing_summary": {
            "list_total": list_total,
            "requested_discount_pct": req_disc,
            "applied_discount_pct": req_disc,
            "discount_amount": disc_amount,
            "net_total": net_total,
            "estimated_cost": total_cost,
            "gross_margin_pct": margin_pct,
            "budget_vnd": budget_vnd,
            "budget_diff_vnd": budget_diff,
            "within_budget": within_budget,
            "price_version": ", ".join(sorted(price_versions)) or "Bảng giá hiện hành",
        },
        "timeline_summary": {
            "requested_days": req_days,
            "target_date": extracted["target_date"],
            "deadline_note": extracted["deadline_note"],
            "feasible_days": max_feasible_days,
            "immediate_delivery_days": immediate_days,
            "is_feasible": is_feasible,
            "gap_days": gap_days,
        },
        "approval_summary": {
            "requires_manager_approval": requires_escalation,
            "escalation_level": escalation_level,
            "reasons": escalation_reasons,
            "status": approval_status,
            "policy_rule": tier,
            "recommended_max_discount": recommended_max_disc,
        },
        "alerts": {
            "old_price_alerts": old_price_alerts,
            "stock_alerts": stock_alerts,
            "unmatched_count": len(unmatched_items),
            "deadline_risk": not is_feasible,
            "missing_info_risk": False,
        },
        "recommendations": business_recs,
        "workflow_stage": stage_label,
        "workflow_stage_code": stage_code,
        "workflow_trace": workflow_trace,
        "next_action": next_action,
        "followup_date": followup_date,
        "priority": priority,
        "manager_decision": None,
    }
    opp["customer_response_draft"] = _build_quotation_draft(opp)
    return opp


def process_batch(
    requests: List[Dict[str, Any]],
    catalog: List[Dict[str, Any]],
    policy: Dict[str, Any],
    sales_team: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Process a batch of customer requests and build executive analytics for Ban Giám đốc."""
    team_state = copy.deepcopy(sales_team)
    opportunities: List[Dict[str, Any]] = []

    for idx, req in enumerate(requests, start=1):
        opp = evaluate_single_request(req, idx, catalog, policy, team_state)
        opportunities.append(opp)

    summary = build_executive_summary(opportunities, team_state)
    return {
        "opportunities": opportunities,
        "summary": summary,
        "sales_team_load": team_state,
    }


def apply_manager_decision(
    opp: Dict[str, Any],
    decision: str,
    approved_discount: Optional[float] = None,
    manager_note: str = "",
) -> Dict[str, Any]:
    """Apply Sales Manager decision at 'Trưởng phòng duyệt' and advance to 'Kết thúc: Cập nhật & Theo dõi'."""
    updated = copy.deepcopy(opp)
    pricing = updated["pricing_summary"]
    list_total = pricing["list_total"]
    total_cost = pricing["estimated_cost"]

    if decision == "approve":
        final_disc = pricing["requested_discount_pct"] if approved_discount is None else float(approved_discount)
        disc_amount = int(round(list_total * final_disc / 100.0))
        net_total = max(0, list_total - disc_amount)
        margin_pct = round(((net_total - total_cost) / net_total) * 100, 1) if net_total > 0 else 0.0

        pricing["applied_discount_pct"] = final_disc
        pricing["discount_amount"] = disc_amount
        pricing["net_total"] = net_total
        pricing["gross_margin_pct"] = margin_pct
        if pricing["budget_vnd"] is not None:
            pricing["budget_diff_vnd"] = net_total - pricing["budget_vnd"]
            pricing["within_budget"] = net_total <= pricing["budget_vnd"]

        updated["approval_summary"]["status"] = "Đã duyệt"
        updated["workflow_stage"] = "Đã duyệt & Cập nhật theo dõi"
        updated["workflow_stage_code"] = "KET_THUC_THEO_DOI"
        updated["next_action"] = "Gửi báo giá đã duyệt cho khách hàng & theo dõi ký hợp đồng"
        updated["manager_decision"] = {
            "decision": "approve",
            "approved_discount_pct": final_disc,
            "note": manager_note or "Trưởng phòng Kinh doanh đã phê duyệt.",
            "decided_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        updated["workflow_trace"] = [
            {"node": "TIEP_NHAN", "label": "Bắt đầu: Tiếp nhận yêu cầu", "status": "completed"},
            {"node": "PHAN_LOAI_KIEM_TRA", "label": "Phân loại & Kiểm tra thông tin", "status": "completed"},
            {"node": "DU_THONG_TIN", "label": "Có đủ thông tin?", "status": "branch_yes", "decision": "Có"},
            {"node": "TAO_HO_SO_CO_HOI", "label": "Tạo Hồ sơ Cơ hội & Gán người phụ trách", "status": "completed"},
            {"node": "THAM_DINH_TON_KHO_GIA", "label": "Thẩm định tồn kho & giá (NVKD & Vận hành)", "status": "completed"},
            {"node": "LAP_BAO_GIA_DE_XUAT", "label": "Lập Báo giá & Dự thảo đề xuất", "status": "completed"},
            {"node": "VUOT_THAM_QUYEN", "label": "Có vượt thẩm quyền / CK đặc biệt?", "status": "branch_yes", "decision": "Có"},
            {"node": "TRUONG_PHONG_DUYET", "label": "Trưởng phòng duyệt", "status": "completed"},
            {"node": "KET_THUC_THEO_DOI", "label": "Kết thúc: Cập nhật & Theo dõi", "status": "completed"},
        ]
        updated["customer_response_draft"] = _build_quotation_draft(updated)
    else:
        updated["approval_summary"]["status"] = "Từ chối vượt trần - Cần thương lượng lại"
        updated["workflow_stage"] = "Cần điều chỉnh đề xuất (Trưởng phòng trả lại)"
        updated["workflow_stage_code"] = "LAP_BAO_GIA_DE_XUAT"
        updated["next_action"] = "NVKD liên hệ khách hàng thương lượng lại mức chiết khấu theo trần duyệt"
        updated["manager_decision"] = {
            "decision": "reject",
            "approved_discount_pct": approved_discount,
            "note": manager_note or "Không duyệt mức chiết khấu vượt trần; đề nghị thương lượng phương án khác.",
            "decided_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    return updated


def build_executive_summary(
    opportunities: List[Dict[str, Any]],
    team_state: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute executive KPIs, workflow stage counts, and risk prevention metrics."""
    total = len(opportunities)
    incomplete = [o for o in opportunities if not o["has_complete_info"]]
    ready = [o for o in opportunities if o["workflow_stage_code"] == "KET_THUC_THEO_DOI"]
    pending_mgr = [o for o in opportunities if o["workflow_stage_code"] == "TRUONG_PHONG_DUYET"]
    rework = [o for o in opportunities if o["workflow_stage_code"] == "LAP_BAO_GIA_DE_XUAT"]

    total_pipeline_vnd = sum(o["pricing_summary"]["net_total"] for o in opportunities if o["has_complete_info"])
    total_list_vnd = sum(o["pricing_summary"]["list_total"] for o in opportunities)

    risk_deadline = sum(1 for o in opportunities if o["alerts"]["deadline_risk"])
    risk_stock = sum(1 for o in opportunities if o["alerts"]["stock_alerts"])
    risk_old_price = sum(1 for o in opportunities if o["alerts"]["old_price_alerts"])
    risk_unmatched = sum(o["alerts"]["unmatched_count"] for o in opportunities)
    risk_over_budget = sum(1 for o in opportunities if o["pricing_summary"]["within_budget"] is False)

    stage_counts = {
        "TIEP_NHAN": total,
        "PHAN_LOAI_KIEM_TRA": total,
        "DU_THONG_TIN": total,
        "YEU_CAU_BO_SUNG": len(incomplete),
        "TAO_HO_SO_CO_HOI": total - len(incomplete),
        "THAM_DINH_TON_KHO_GIA": total - len(incomplete),
        "LAP_BAO_GIA_DE_XUAT": (total - len(incomplete)),
        "VUOT_THAM_QUYEN": total - len(incomplete),
        "TRUONG_PHONG_DUYET": len(pending_mgr),
        "KET_THUC_THEO_DOI": len(ready),
    }

    return {
        "total_requests": total,
        "complete_requests": total - len(incomplete),
        "incomplete_requests": len(incomplete),
        "pending_manager_approval": len(pending_mgr),
        "ready_to_send": len(ready),
        "rework_count": len(rework),
        "total_pipeline_vnd": total_pipeline_vnd,
        "total_list_vnd": total_list_vnd,
        "risk_metrics": {
            "deadline_conflicts": risk_deadline,
            "stock_shortages": risk_stock,
            "old_price_prevented": risk_old_price,
            "unmatched_items_flagged": risk_unmatched,
            "over_budget_deals": risk_over_budget,
            "tracked_incomplete_pct": 100 if incomplete else 100,
        },
        "stage_counts": stage_counts,
        "sales_team_load": team_state,
    }

