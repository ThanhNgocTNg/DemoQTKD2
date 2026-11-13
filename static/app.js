(() => {
  "use strict";

  const state = {
    workspace: null,
    selectedOppId: null,
    activeDetailTab: "analysis",
    stageFilter: "ALL",
    searchQuery: "",
    queuedFiles: [],
    llmConfig: loadLlmConfig(),
  };

  function loadLlmConfig() {
    try {
      const raw = localStorage.getItem("minhan_llm_config");
      return raw ? JSON.parse(raw) : { provider: "gemini", model: "gemini-2.5-flash", api_key: "", base_url: "" };
    } catch {
      return { provider: "gemini", model: "gemini-2.5-flash", api_key: "", base_url: "" };
    }
  }

  function saveLlmConfig(cfg) {
    state.llmConfig = cfg;
    localStorage.setItem("minhan_llm_config", JSON.stringify(cfg));
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatVnd(val) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) return "Chưa xác định";
    return Math.round(Number(val)).toLocaleString("vi-VN") + " đ";
  }

  function formatShortVnd(val) {
    if (!val) return "0 đ";
    if (val >= 1_000_000_000) return (val / 1_000_000_000).toFixed(2).replace(".", ",") + " tỷ";
    if (val >= 1_000_000) return Math.round(val / 1_000_000).toLocaleString("vi-VN") + " tr";
    return formatVnd(val);
  }

  function showToast(message, type = "info") {
    const area = document.getElementById("toast-area");
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    area.appendChild(el);
    setTimeout(() => {
      el.remove();
    }, 4500);
  }

  async function apiJson(url, options = {}) {
    const resp = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await resp.json();
    if (!resp.ok || data.ok === false) {
      throw new Error(data.error || `Lỗi máy chủ (${resp.status})`);
    }
    return data;
  }

  function setWorkspace(ws, preferredOppId = null) {
    state.workspace = ws;
    if (preferredOppId) {
      state.selectedOppId = preferredOppId;
    } else if (!ws.opportunities.some((o) => o.opportunity_id === state.selectedOppId)) {
      state.selectedOppId = ws.opportunities[0] ? ws.opportunities[0].opportunity_id : null;
    }
    renderAll();
  }

  function renderAll() {
    if (!state.workspace) return;
    document.getElementById("source-badge").textContent = state.workspace.source_info?.label || "Sẵn sàng";
    renderKpisAndTeam();
    renderWorkflowDiagram();
    renderOpportunityList();
    renderSelectedDetail();
    renderKnowledgeBase();
  }

  function renderKpisAndTeam() {
    const sum = state.workspace.summary;
    const rm = sum.risk_metrics || {};
    const kpiContainer = document.getElementById("kpi-cards");

    const cards = [
      {
        label: "Tổng yêu cầu đã xử lý",
        value: `${sum.total_requests} hồ sơ`,
        sub: `${sum.complete_requests} đủ thông tin • ${sum.incomplete_requests} cần KH bổ sung`,
      },
      {
        label: "Tổng giá trị cơ hội dự kiến",
        value: formatShortVnd(sum.total_pipeline_vnd),
        sub: `${sum.ready_to_send} sẵn sàng gửi • ${sum.pending_manager_approval} chờ TP duyệt`,
      },
      {
        label: "Rủi ro báo giá & tiến độ ngăn chặn",
        value: `${rm.old_price_prevented || 0} giá cũ • ${rm.deadline_conflicts || 0} trễ hạn`,
        sub: `${rm.stock_shortages || 0} cảnh báo tồn kho • ${rm.unmatched_items_flagged || 0} hạng mục ngoài DM`,
      },
      {
        label: "Kiểm soát theo dõi & Vượt ngân sách",
        value: `100% có người theo dõi`,
        sub: `${rm.over_budget_deals || 0} hồ sơ vượt ngân sách (đã đề xuất tối ưu)`,
      },
    ];

    kpiContainer.innerHTML = cards
      .map(
        (c) => `
      <div class="kpi-box">
        <div class="kpi-label">${escapeHtml(c.label)}</div>
        <div class="kpi-value">${escapeHtml(c.value)}</div>
        <div class="kpi-sub">${escapeHtml(c.sub)}</div>
      </div>`
      )
      .join("");

    const teamContainer = document.getElementById("team-load-bars");
    const team = state.workspace.sales_team_load || [];
    teamContainer.innerHTML = team
      .map((rep) => {
        const cap = Math.max(1, rep.weekly_capacity || 30);
        const pct = Math.min(100, Math.round((rep.active_deals / cap) * 100));
        return `
        <div class="team-bar-row" title="${escapeHtml(rep.specialty)}">
          <div class="team-bar-name">${escapeHtml(rep.name)}</div>
          <div class="progress-track">
            <div class="progress-fill ${pct >= 85 ? "high" : ""}" style="width: ${pct}%"></div>
          </div>
          <div class="team-bar-count">${rep.active_deals}/${cap} hồ sơ</div>
        </div>`;
      })
      .join("");
  }

  function renderWorkflowDiagram() {
    const counts = state.workspace.summary.stage_counts || {};
    const selectedOpp = getSelectedOpportunity();
    const visitedNodes = new Set((selectedOpp?.workflow_trace || []).map((t) => t.node));
    const activeStageCode = selectedOpp?.workflow_stage_code || null;

    const nodeClass = (nodeId) => {
      if (!selectedOpp) return "wf-node";
      if (activeStageCode === nodeId) return "wf-node highlighted";
      if (visitedNodes.has(nodeId)) return "wf-node";
      return "wf-node dimmed";
    };

    const countPill = (x, y, val, bg = "#1d6fd8") => `
      <g transform="translate(${x}, ${y})">
        <rect x="0" y="0" width="28" height="18" rx="9" fill="${bg}"></rect>
        <text x="14" y="12.5" text-anchor="middle" fill="#ffffff" font-size="10.5" font-weight="700">${val ?? 0}</text>
      </g>`;

    const svg = `
    <svg class="wf-svg" viewBox="0 0 780 515" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrowBlue" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#1d6fd8" />
        </marker>
      </defs>

      <!-- Loop back arrow from Yêu cầu KH làm rõ -> Bắt đầu & Có đủ thông tin -->
      <path d="M 640 24 L 640 12 L 155 12 L 155 18" fill="none" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <path d="M 390 12 L 390 88" fill="none" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />

      <!-- Bắt đầu -> Phân loại -->
      <line x1="155" y1="68" x2="155" y2="92" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <!-- Phân loại -> Có đủ thông tin? -->
      <line x1="265" y1="122" x2="306" y2="122" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />

      <!-- Có đủ thông tin? -> Không -> Yêu cầu KH làm rõ -->
      <path d="M 468 122 L 640 122 L 640 76" fill="none" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <text x="545" y="114" fill="#a71818" font-size="12" font-weight="700">Không</text>

      <!-- Có đủ thông tin? -> Có -> Tạo Hồ sơ Cơ hội -->
      <line x1="390" y1="154" x2="390" y2="178" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <text x="400" y="170" fill="#116f33" font-size="12" font-weight="700">Có</text>

      <!-- Tạo Hồ sơ -> Thẩm định -> Lập báo giá -> Vượt thẩm quyền? -->
      <line x1="390" y1="216" x2="390" y2="232" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <line x1="390" y1="270" x2="390" y2="286" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <line x1="390" y1="324" x2="390" y2="340" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />

      <!-- Vượt thẩm quyền? -> Có -> Trưởng phòng duyệt -->
      <line x1="478" y1="378" x2="538" y2="378" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <text x="492" y="370" fill="#9a5104" font-size="12" font-weight="700">Có</text>
      <path d="M 615 402 L 615 446 L 494 446" fill="none" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />

      <!-- Vượt thẩm quyền? -> Không -> Kết thúc -->
      <line x1="390" y1="414" x2="390" y2="438" stroke="#1d6fd8" stroke-width="2" marker-end="url(#arrowBlue)" />
      <text x="400" y="430" fill="#116f33" font-size="12" font-weight="700">Không</text>

      <!-- NODE 1: Bắt đầu: Tiếp nhận yêu cầu -->
      <g class="${nodeClass("TIEP_NHAN")}" data-stage="ALL">
        <rect x="45" y="22" width="220" height="46" rx="23" fill="#b7e4b9" stroke="#2d7a47" stroke-width="1.8" />
        <text x="155" y="42" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Bắt đầu:</text>
        <text x="155" y="58" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Tiếp nhận yêu cầu</text>
        ${countPill(242, 16, counts.TIEP_NHAN, "#16a34a")}
      </g>

      <!-- NODE 2: Phân loại & Kiểm tra thông tin -->
      <g class="${nodeClass("PHAN_LOAI_KIEM_TRA")}" data-stage="ALL">
        <rect x="45" y="96" width="220" height="50" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="155" y="118" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Phân loại &amp; Kiểm tra</text>
        <text x="155" y="135" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">thông tin</text>
        <text x="155" y="160" text-anchor="middle" fill="#5a6b82" font-size="11">Đầy đủ thông tin?</text>
      </g>

      <!-- DECISION 1: Có đủ thông tin? -->
      <g class="${nodeClass("DU_THONG_TIN")}" data-stage="ALL">
        <polygon points="390,90 470,122 390,154 310,122" fill="#fce4b8" stroke="#d97706" stroke-width="1.8" />
        <text x="390" y="118" text-anchor="middle" fill="#132238" font-size="12" font-weight="700">Có đủ</text>
        <text x="390" y="134" text-anchor="middle" fill="#132238" font-size="12" font-weight="700">thông tin?</text>
      </g>

      <!-- NODE 3: Yêu cầu KH làm rõ / bổ sung -->
      <g class="${nodeClass("YEU_CAU_BO_SUNG")}" data-stage="YEU_CAU_BO_SUNG">
        <rect x="530" y="24" width="218" height="48" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="639" y="45" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Yêu cầu KH</text>
        <text x="639" y="61" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">làm rõ / bổ sung</text>
        ${countPill(724, 16, counts.YEU_CAU_BO_SUNG, "#d97706")}
      </g>

      <!-- NODE 4: Tạo Hồ sơ Cơ hội & Gán người phụ trách -->
      <g class="${nodeClass("TAO_HO_SO_CO_HOI")}" data-stage="COMPLETE_ONLY">
        <rect x="260" y="180" width="260" height="36" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="390" y="202" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Tạo Hồ sơ Cơ hội &amp; Gán người phụ trách</text>
        ${countPill(504, 173, counts.TAO_HO_SO_CO_HOI, "#1d6fd8")}
      </g>

      <!-- NODE 5: Thẩm định tồn kho & giá -->
      <g class="${nodeClass("THAM_DINH_TON_KHO_GIA")}" data-stage="COMPLETE_ONLY">
        <rect x="275" y="234" width="230" height="36" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="390" y="256" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Thẩm định tồn kho &amp; giá</text>
        <text x="516" y="248" fill="#5a6b82" font-size="11.5" font-weight="600">NVKD &amp; Bộ phận</text>
        <text x="516" y="263" fill="#5a6b82" font-size="11.5" font-weight="600">Vận hành</text>
      </g>

      <!-- NODE 6: Lập Báo giá & Dự thảo đề xuất -->
      <g class="${nodeClass("LAP_BAO_GIA_DE_XUAT")}" data-stage="COMPLETE_ONLY">
        <rect x="275" y="288" width="230" height="36" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="390" y="310" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Lập Báo giá &amp; Dự thảo đề xuất</text>
      </g>

      <!-- DECISION 2: Có vượt thẩm quyền / Cần chiết khấu đặc biệt? -->
      <g class="${nodeClass("VUOT_THAM_QUYEN")}" data-stage="COMPLETE_ONLY">
        <polygon points="390,342 480,378 390,414 300,378" fill="#fce4b8" stroke="#d97706" stroke-width="1.8" />
        <text x="390" y="369" text-anchor="middle" fill="#132238" font-size="11" font-weight="700">Có vượt thẩm quyền /</text>
        <text x="390" y="382" text-anchor="middle" fill="#132238" font-size="11" font-weight="700">Cần chiết khấu đặc</text>
        <text x="390" y="395" text-anchor="middle" fill="#132238" font-size="11" font-weight="700">biệt?</text>
      </g>

      <!-- NODE 7: Trưởng phòng duyệt -->
      <g class="${nodeClass("TRUONG_PHONG_DUYET")}" data-stage="TRUONG_PHONG_DUYET">
        <rect x="540" y="354" width="160" height="48" rx="6" fill="#d9ecff" stroke="#1d6fd8" stroke-width="1.8" />
        <text x="620" y="375" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Trưởng phòng</text>
        <text x="620" y="391" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">duyệt</text>
        ${countPill(682, 345, counts.TRUONG_PHONG_DUYET, "#7c3aed")}
      </g>

      <!-- NODE 8: Kết thúc: Cập nhật & Theo dõi -->
      <g class="${nodeClass("KET_THUC_THEO_DOI")}" data-stage="KET_THUC_THEO_DOI">
        <rect x="288" y="442" width="204" height="46" rx="23" fill="#f7a8a3" stroke="#b91c1c" stroke-width="1.8" />
        <text x="390" y="462" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Kết thúc:</text>
        <text x="390" y="478" text-anchor="middle" fill="#132238" font-size="12.5" font-weight="700">Cập nhật &amp; Theo dõi</text>
        ${countPill(472, 434, counts.KET_THUC_THEO_DOI, "#16a34a")}
      </g>
    </svg>`;

    const container = document.getElementById("workflow-diagram");
    container.innerHTML = svg;
    container.querySelectorAll(".wf-node").forEach((el) => {
      el.addEventListener("click", () => {
        const st = el.getAttribute("data-stage");
        if (!st) return;
        state.stageFilter = st === "COMPLETE_ONLY" ? "ALL" : st;
        document.getElementById("filter-stage").value =
          ["ALL", "KET_THUC_THEO_DOI", "TRUONG_PHONG_DUYET", "YEU_CAU_BO_SUNG"].includes(state.stageFilter)
            ? state.stageFilter
            : "ALL";
        document.getElementById("btn-clear-stage-filter").classList.toggle("hidden", state.stageFilter === "ALL");
        renderOpportunityList();
      });
    });
  }

  function getFilteredOpportunities() {
    const all = state.workspace?.opportunities || [];
    const q = state.searchQuery.trim().toLowerCase();
    return all.filter((o) => {
      if (state.stageFilter === "RISK_ONLY") {
        const hasRisk =
          o.alerts.deadline_risk ||
          o.alerts.stock_alerts.length > 0 ||
          o.alerts.old_price_alerts.length > 0 ||
          o.alerts.unmatched_count > 0 ||
          o.alerts.missing_info_risk ||
          o.pricing_summary.within_budget === false;
        if (!hasRisk) return false;
      } else if (state.stageFilter !== "ALL" && o.workflow_stage_code !== state.stageFilter) {
        return false;
      }

      if (q) {
        const hay = [
          o.opportunity_id,
          o.request_id,
          o.customer_name,
          o.assigned_rep?.name,
          o.request_text,
          ...(o.line_items || []).map((it) => it.product_name),
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function getSelectedOpportunity() {
    const all = state.workspace?.opportunities || [];
    return all.find((o) => o.opportunity_id === state.selectedOppId) || null;
  }

  function renderOpportunityList() {
    const list = getFilteredOpportunities();
    document.getElementById("filtered-count-badge").textContent = `${list.length} hồ sơ`;
    const container = document.getElementById("opportunity-list");
    if (!list.length) {
      container.innerHTML = `<p class="muted-empty">Không có hồ sơ nào phù hợp bộ lọc hiện tại.</p>`;
      return;
    }

    container.innerHTML = list
      .map((o) => {
        const isSelected = o.opportunity_id === state.selectedOppId;
        const ps = o.pricing_summary;
        const ts = o.timeline_summary;
        const stageBadge =
          o.workflow_stage_code === "KET_THUC_THEO_DOI"
            ? `<span class="badge badge-green">${escapeHtml(o.workflow_stage)}</span>`
            : o.workflow_stage_code === "TRUONG_PHONG_DUYET"
            ? `<span class="badge badge-purple">${escapeHtml(o.workflow_stage)}</span>`
            : `<span class="badge badge-amber">${escapeHtml(o.workflow_stage)}</span>`;

        const riskBadges = [];
        if (o.alerts.deadline_risk) riskBadges.push(`<span class="badge badge-red">Trễ hạn (+${ts.gap_days}d)</span>`);
        if (o.alerts.stock_alerts.length) riskBadges.push(`<span class="badge badge-amber">Thiếu tồn kho</span>`);
        if (o.alerts.old_price_alerts.length) riskBadges.push(`<span class="badge badge-blue">Cảnh báo giá cũ</span>`);
        if (o.alerts.unmatched_count) riskBadges.push(`<span class="badge badge-red">${o.alerts.unmatched_count} HM ngoài DM</span>`);
        if (ps.within_budget === false) riskBadges.push(`<span class="badge badge-red">Vượt ngân sách</span>`);

        return `
        <div class="opp-card ${isSelected ? "selected" : ""}" data-opp-id="${escapeHtml(o.opportunity_id)}">
          <div class="opp-card-top">
            <span class="opp-id">${escapeHtml(o.opportunity_id)} • ${escapeHtml(o.request_id)}</span>
            ${stageBadge}
          </div>
          <div class="opp-customer">${escapeHtml(o.customer_name)}</div>
          <div class="opp-meta">
            <span>Phụ trách: <strong>${escapeHtml(o.assigned_rep.name)}</strong></span>
            <span><strong>${ps.net_total > 0 ? formatShortVnd(ps.net_total) : "Chưa định giá"}</strong></span>
          </div>
          <div class="opp-badges">
            <span class="badge badge-gray">${o.line_items.length + o.unmatched_items.length} hạng mục</span>
            ${ps.requested_discount_pct > 0 ? `<span class="badge badge-gray">CK ${ps.applied_discount_pct}%</span>` : ""}
            ${riskBadges.join("")}
          </div>
        </div>`;
      })
      .join("");

    container.querySelectorAll(".opp-card").forEach((el) => {
      el.addEventListener("click", () => {
        state.selectedOppId = el.getAttribute("data-opp-id");
        renderWorkflowDiagram();
        renderOpportunityList();
        renderSelectedDetail();
      });
    });
  }

  function renderSelectedDetail() {
    const opp = getSelectedOpportunity();
    const container = document.getElementById("opportunity-detail");
    if (!opp) {
      container.innerHTML = `<p class="muted-empty">Chọn một hồ sơ ở danh sách bên trái để xem phân tích chi tiết.</p>`;
      return;
    }

    const ps = opp.pricing_summary;
    const ts = opp.timeline_summary;
    const ap = opp.approval_summary;

    const traceHtml = (opp.workflow_trace || [])
      .map((t) => {
        const cls = t.status === "active" ? "active" : t.status === "completed" || t.status === "branch_yes" ? "done" : "";
        const dec = t.decision ? ` (${t.decision})` : "";
        return `<span class="trace-pill ${cls}">${escapeHtml(t.label + dec)}</span>`;
      })
      .join(" → ");

    let actionBanner = "";
    if (!opp.has_complete_info) {
      actionBanner = `
      <div class="action-box warning">
        <h4>Hồ sơ đang ở nhánh: Yêu cầu KH làm rõ / bổ sung (Người theo dõi: ${escapeHtml(opp.assigned_rep.name)})</h4>
        <p style="margin:0 0 6px;"><strong>Thông tin còn thiếu:</strong> ${opp.missing_fields.map(escapeHtml).join(" • ")}</p>
        <p style="margin:0;font-size:12.5px;">Sau khi khách hàng phản hồi, nhập thông tin bổ sung bên dưới để chạy lại quy trình từ bước Tiếp nhận:</p>
        <div class="inline-form-grid">
          <input id="supp-budget" class="input" type="text" placeholder="Ngân sách (VD: 450 triệu)" value="${ps.budget_vnd ? escapeHtml(String(ps.budget_vnd)) : ""}" />
          <input id="supp-approver" class="input" type="text" placeholder="Người phê duyệt (VD: Anh Minh - GĐ)" value="${escapeHtml(opp.approver || "")}" />
          <input id="supp-deadline" class="input" type="text" placeholder="Thời hạn (VD: 14 ngày)" value="${ts.requested_days ? escapeHtml(ts.requested_days + " ngày") : ""}" />
        </div>
        <div style="display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap;">
          <input id="supp-extra" class="input" style="flex:1;min-width:220px;" type="text" placeholder="Ghi chú/sản phẩm bổ sung thêm (nếu có, VD: 15 bộ phát Wi-Fi Aruba AP22)" />
          <button id="btn-submit-supplement" class="btn btn-primary btn-sm" type="button">Cập nhật &amp; Chạy lại luồng</button>
        </div>
      </div>`;
    } else if (opp.workflow_stage_code === "TRUONG_PHONG_DUYET") {
      actionBanner = `
      <div class="action-box escalation">
        <h4>Cần phê duyệt vượt thẩm quyền: ${escapeHtml(ap.escalation_level)}</h4>
        <ul class="alert-list" style="margin-bottom:10px;">
          ${ap.reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}
        </ul>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <label style="font-size:12.5px;font-weight:600;">% Chiết khấu duyệt:
            <input id="mgr-approved-disc" class="input" style="width:90px;display:inline-block;margin-left:4px;" type="number" step="0.5" min="0" max="50" value="${escapeHtml(String(ap.recommended_max_discount ?? ps.requested_discount_pct))}" />
          </label>
          <input id="mgr-note" class="input" style="flex:1;min-width:200px;" type="text" placeholder="Ghi chú của Trưởng phòng Kinh doanh..." />
          <button id="btn-mgr-approve" class="btn btn-success btn-sm" type="button">Phê duyệt &amp; Chốt báo giá</button>
          <button id="btn-mgr-reject" class="btn btn-danger btn-sm" type="button">Trả lại NVKD thương lượng</button>
        </div>
      </div>`;
    }

    const alertsAll = [
      ...opp.alerts.old_price_alerts,
      ...opp.alerts.stock_alerts,
      ...(opp.unmatched_items.length
        ? [`Phát hiện ${opp.unmatched_items.length} hạng mục ngoài danh mục chuẩn chưa có SKU — đã tách riêng để tránh bỏ sót.`]
        : []),
    ];

    const budgetText = ps.budget_vnd
      ? `${formatShortVnd(ps.budget_vnd)} (${ps.within_budget ? "Phù hợp" : "Vượt " + formatShortVnd(ps.budget_diff_vnd)})`
      : "Chưa có ngân sách";

    const deadlineText = ts.requested_days
      ? `KH cần ${ts.requested_days} ngày / Đáp ứng ${ts.feasible_days} ngày`
      : `Cần ${ts.feasible_days} ngày triển khai`;

    const tabAnalysis = `
      <div class="summary-grid-4">
        <div class="mini-stat">
          <div class="mini-stat-label">Giá trị đề xuất (sau CK ${ps.applied_discount_pct}%)</div>
          <div class="mini-stat-val">${formatVnd(ps.net_total)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-stat-label">So với ngân sách tổng</div>
          <div class="mini-stat-val" style="color:${ps.within_budget === false ? "var(--red)" : "var(--text)"}">${escapeHtml(budgetText)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-stat-label">Thời hạn &amp; Khả năng đáp ứng</div>
          <div class="mini-stat-val" style="color:${ts.is_feasible ? "var(--green)" : "var(--red)"}">${escapeHtml(deadlineText)}</div>
        </div>
        <div class="mini-stat">
          <div class="mini-stat-label">Biên lợi nhuận gộp / Thẩm quyền</div>
          <div class="mini-stat-val">${ps.gross_margin_pct}% • ${escapeHtml(ap.escalation_level)}</div>
        </div>
      </div>

      ${
        alertsAll.length
          ? `<div class="alert-panel">
              <strong>Cảnh báo thẩm định (Giá, Tồn kho, Tiến độ, Hạng mục):</strong>
              <ul class="alert-list">${alertsAll.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul>
            </div>`
          : ""
      }

      <div class="rec-panel">
        <strong>Phân tích &amp; Đề xuất Kinh doanh của AI Agent:</strong>
        <ul class="rec-list">${opp.recommendations.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      </div>

      <div>
        <div class="field-label">Yêu cầu khách hàng gốc (${escapeHtml(opp.channel)} • Ngày nhận: ${escapeHtml(opp.received_date)})</div>
        <div class="raw-request-box">${escapeHtml(opp.request_text)}</div>
      </div>
    `;

    const tabAudit = `
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>Mã SKU</th>
              <th>Sản phẩm / Dịch vụ</th>
              <th>SL</th>
              <th>Đơn giá (${escapeHtml(ps.price_version)})</th>
              <th>Thành tiền</th>
              <th>Tồn khả dụng</th>
              <th>Đáp ứng (ngày)</th>
            </tr>
          </thead>
          <tbody>
            ${
              opp.line_items.length
                ? opp.line_items
                    .map(
                      (it) => `
                  <tr>
                    <td><code>${escapeHtml(it.sku)}</code></td>
                    <td>
                      <strong>${escapeHtml(it.product_name)}</strong>
                      ${it.old_price_warning ? `<div style="color:var(--blue);font-size:11.5px;margin-top:2px;">⚠ ${escapeHtml(it.old_price_warning)}</div>` : ""}
                    </td>
                    <td>${it.quantity} ${escapeHtml(it.unit)}</td>
                    <td>${formatVnd(it.unit_price)}</td>
                    <td><strong>${formatVnd(it.line_total)}</strong></td>
                    <td>
                      ${it.stock_available}
                      <div><span class="badge ${it.shortage_qty > 0 ? "badge-amber" : "badge-green"}">${escapeHtml(it.stock_status)}</span></div>
                    </td>
                    <td>${it.item_feasible_days} ngày<div style="font-size:11px;color:var(--muted);">Nhập ${it.restock_days}d + TK ${it.deploy_days}d</div></td>
                  </tr>`
                    )
                    .join("")
                : `<tr><td colspan="7" class="muted-empty">Chưa trích xuất được sản phẩm khớp danh mục.</td></tr>`
            }
          </tbody>
        </table>
      </div>
      ${
        opp.unmatched_items.length
          ? `<div class="alert-panel" style="margin-top:12px;">
              <strong>Hạng mục phát hiện trong văn bản nhưng chưa có trong Danh mục chuẩn (Giữ lại để tránh bỏ sót):</strong>
              <ul class="alert-list">
                ${opp.unmatched_items.map((u) => `<li><strong>${escapeHtml(u.raw_text)}</strong> (SL: ${u.quantity}) — ${escapeHtml(u.reason)}</li>`).join("")}
              </ul>
            </div>`
          : ""
      }
    `;

    const tabDraft = `
      <div class="draft-toolbar">
        <span class="section-desc">Bản nháp phản hồi khách hàng tự động theo kết quả thẩm định hiện tại (có thể chỉnh sửa trước khi sao chép gửi email):</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button id="btn-refine-llm" class="btn btn-outline btn-sm" type="button">Viết lại mượt hơn (LLM)</button>
          <button id="btn-copy-draft" class="btn btn-primary btn-sm" type="button">Sao chép bản nháp</button>
        </div>
      </div>
      <textarea id="draft-textarea" class="draft-box">${escapeHtml(opp.customer_response_draft)}</textarea>
    `;

    const crmRecord = {
      opportunity_id: opp.opportunity_id,
      request_id: opp.request_id,
      customer_name: opp.customer_name,
      contact_name: opp.contact_name,
      approver: opp.approver || "(Chưa xác định)",
      assigned_sales_rep: opp.assigned_rep,
      workflow_stage: opp.workflow_stage,
      priority: opp.priority,
      next_action: opp.next_action,
      followup_date: opp.followup_date,
      pricing_summary: opp.pricing_summary,
      timeline_summary: opp.timeline_summary,
      approval_summary: opp.approval_summary,
      manager_decision: opp.manager_decision,
    };

    const tabCrm = `
      <div class="summary-grid-4">
        <div class="mini-stat"><div class="mini-stat-label">Mã Hồ sơ Cơ hội</div><div class="mini-stat-val">${escapeHtml(opp.opportunity_id)}</div></div>
        <div class="mini-stat"><div class="mini-stat-label">Người phụ trách / Theo dõi</div><div class="mini-stat-val">${escapeHtml(opp.assigned_rep.name)}</div></div>
        <div class="mini-stat"><div class="mini-stat-label">Ngày theo dõi tiếp theo</div><div class="mini-stat-val">${escapeHtml(opp.followup_date)}</div></div>
        <div class="mini-stat"><div class="mini-stat-label">Mức ưu tiên</div><div class="mini-stat-val">${escapeHtml(opp.priority)}</div></div>
      </div>
      <div class="rec-panel">
        <strong>Hành động tiếp theo:</strong> ${escapeHtml(opp.next_action)}
      </div>
      <div class="field-label">Dữ liệu Hồ sơ Cơ hội chuẩn hóa (CRM Payload)</div>
      <pre class="raw-request-box" style="max-height:280px;overflow:auto;">${escapeHtml(JSON.stringify(crmRecord, null, 2))}</pre>
    `;

    container.innerHTML = `
      <div class="detail-header">
        <div>
          <h3 class="detail-title">${escapeHtml(opp.customer_name)}</h3>
          <div class="detail-subtitle">
            Hồ sơ <strong>${escapeHtml(opp.opportunity_id)}</strong> • Yêu cầu <strong>${escapeHtml(opp.request_id)}</strong> •
            Phụ trách: <strong>${escapeHtml(opp.assigned_rep.name)} (${escapeHtml(opp.assigned_rep.rep_id)})</strong> •
            Người duyệt phía KH: <strong>${escapeHtml(opp.approver || "Chưa xác định")}</strong>
          </div>
        </div>
        <span class="badge ${opp.workflow_stage_code === "KET_THUC_THEO_DOI" ? "badge-green" : opp.workflow_stage_code === "TRUONG_PHONG_DUYET" ? "badge-purple" : "badge-amber"}">
          ${escapeHtml(opp.workflow_stage)}
        </span>
      </div>

      <div class="trace-pills">${traceHtml}</div>
      ${actionBanner}

      <div class="detail-tabs">
        <button class="detail-tab-btn ${state.activeDetailTab === "analysis" ? "active" : ""}" data-dtab="analysis" type="button">Phân tích &amp; Đề xuất Kinh doanh</button>
        <button class="detail-tab-btn ${state.activeDetailTab === "audit" ? "active" : ""}" data-dtab="audit" type="button">Thẩm định Giá &amp; Tồn kho (${opp.line_items.length + opp.unmatched_items.length})</button>
        <button class="detail-tab-btn ${state.activeDetailTab === "draft" ? "active" : ""}" data-dtab="draft" type="button">Bản nháp Phản hồi Khách hàng</button>
        <button class="detail-tab-btn ${state.activeDetailTab === "crm" ? "active" : ""}" data-dtab="crm" type="button">Hồ sơ Cơ hội (CRM)</button>
      </div>

      <div id="dtab-body">
        ${
          state.activeDetailTab === "analysis"
            ? tabAnalysis
            : state.activeDetailTab === "audit"
            ? tabAudit
            : state.activeDetailTab === "draft"
            ? tabDraft
            : tabCrm
        }
      </div>
    `;

    container.querySelectorAll(".detail-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.activeDetailTab = btn.getAttribute("data-dtab");
        renderSelectedDetail();
      });
    });

    const btnSupplement = document.getElementById("btn-submit-supplement");
    if (btnSupplement) {
      btnSupplement.addEventListener("click", async () => {
        try {
          const res = await apiJson("/api/opportunity/supplement", {
            method: "POST",
            body: JSON.stringify({
              opportunity_id: opp.opportunity_id,
              budget: document.getElementById("supp-budget").value,
              approver: document.getElementById("supp-approver").value,
              deadline: document.getElementById("supp-deadline").value,
              additional_text: document.getElementById("supp-extra").value,
            }),
          });
          setWorkspace(res.state, res.updated_opportunity.opportunity_id);
          showToast("Đã bổ sung thông tin và chạy lại quy trình từ đầu!", "success");
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    }

    const btnApprove = document.getElementById("btn-mgr-approve");
    if (btnApprove) {
      btnApprove.addEventListener("click", () => submitManagerDecision(opp.opportunity_id, "approve"));
    }
    const btnReject = document.getElementById("btn-mgr-reject");
    if (btnReject) {
      btnReject.addEventListener("click", () => submitManagerDecision(opp.opportunity_id, "reject"));
    }

    const btnCopy = document.getElementById("btn-copy-draft");
    if (btnCopy) {
      btnCopy.addEventListener("click", async () => {
        const txt = document.getElementById("draft-textarea").value;
        try {
          await navigator.clipboard.writeText(txt);
          showToast("Đã sao chép bản nháp phản hồi khách hàng!", "success");
        } catch {
          document.getElementById("draft-textarea").select();
          document.execCommand("copy");
          showToast("Đã sao chép bản nháp!", "success");
        }
      });
    }

    const btnRefine = document.getElementById("btn-refine-llm");
    if (btnRefine) {
      btnRefine.addEventListener("click", async () => {
        if (!state.llmConfig?.api_key) {
          openLlmModal();
          showToast("Hãy nhập API Key trong Cấu hình LLM để dùng tính năng viết lại bằng AI.", "info");
          return;
        }
        btnRefine.disabled = true;
        btnRefine.textContent = "Đang viết lại...";
        try {
          const res = await apiJson("/api/opportunity/refine-draft", {
            method: "POST",
            body: JSON.stringify({
              opportunity_id: opp.opportunity_id,
              llm_config: state.llmConfig,
            }),
          });
          setWorkspace(res.state, opp.opportunity_id);
          showToast("Đã trau chuốt lại bản nháp bằng LLM!", "success");
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          btnRefine.disabled = false;
          btnRefine.textContent = "Viết lại mượt hơn (LLM)";
        }
      });
    }
  }

  async function submitManagerDecision(oppId, decision) {
    const discVal = parseFloat(document.getElementById("mgr-approved-disc")?.value || "0");
    const note = document.getElementById("mgr-note")?.value || "";
    try {
      const res = await apiJson("/api/opportunity/manager-decision", {
        method: "POST",
        body: JSON.stringify({
          opportunity_id: oppId,
          decision,
          approved_discount: Number.isNaN(discVal) ? null : discVal,
          manager_note: note,
        }),
      });
      setWorkspace(res.state, res.updated_opportunity.opportunity_id);
      showToast(
        decision === "approve"
          ? "Trưởng phòng đã phê duyệt và cập nhật bản nháp báo giá!"
          : "Đã trả lại hồ sơ để NVKD thương lượng lại.",
        "success"
      );
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function renderKnowledgeBase() {
    const catalog = state.workspace.catalog || [];
    const policy = state.workspace.policy || {};
    const team = state.workspace.sales_team || [];

    document.getElementById("kb-catalog").innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Mã SP</th>
            <th>Tên sản phẩm / Dịch vụ</th>
            <th>Đơn giá hiện hành (VNĐ)</th>
            <th>Giá cũ</th>
            <th>Tồn khả dụng</th>
            <th>Nhập hàng (ngày)</th>
            <th>Triển khai (ngày)</th>
          </tr>
        </thead>
        <tbody>
          ${catalog
            .map(
              (p, i) => `
            <tr>
              <td><code>${escapeHtml(p.sku)}</code></td>
              <td><strong>${escapeHtml(p.name)}</strong><div style="font-size:11px;color:var(--muted);">${escapeHtml(p.category)}</div></td>
              <td><input class="input kb-cat-input" data-idx="${i}" data-field="current_price" type="number" value="${p.current_price}" style="width:125px" /></td>
              <td>${p.old_price ? formatVnd(p.old_price) : "—"}</td>
              <td><input class="input kb-cat-input" data-idx="${i}" data-field="stock" type="number" value="${p.stock}" style="width:85px" /></td>
              <td><input class="input kb-cat-input" data-idx="${i}" data-field="restock_days" type="number" value="${p.restock_days}" style="width:75px" /></td>
              <td><input class="input kb-cat-input" data-idx="${i}" data-field="deploy_days" type="number" value="${p.deploy_days}" style="width:75px" /></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    const tiers = policy.tiers || [];
    document.getElementById("kb-policy").innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Mã</th>
            <th>Mức chính sách</th>
            <th>NVKD duyệt tối đa (%)</th>
            <th>Trưởng phòng duyệt tối đa (%)</th>
            <th>Cấp duyệt vượt ngưỡng</th>
            <th>Ghi chú</th>
          </tr>
        </thead>
        <tbody>
          ${tiers
            .map(
              (t, i) => `
            <tr>
              <td><code>${escapeHtml(t.rule_id)}</code></td>
              <td><strong>${escapeHtml(t.rule_name)}</strong></td>
              <td><input class="input kb-pol-input" data-idx="${i}" data-field="max_rep_discount" type="number" step="0.5" value="${t.max_rep_discount}" style="width:85px" /></td>
              <td><input class="input kb-pol-input" data-idx="${i}" data-field="max_manager_discount" type="number" step="0.5" value="${t.max_manager_discount}" style="width:85px" /></td>
              <td>${escapeHtml(t.approver_role)}</td>
              <td>${escapeHtml(t.notes)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    document.getElementById("kb-team").innerHTML = `
      <table class="data-table">
        <thead>
          <tr><th>Mã NV</th><th>Họ tên</th><th>Chuyên môn</th><th>Định mức tuần</th><th>Email</th></tr>
        </thead>
        <tbody>
          ${team
            .map(
              (m) => `
            <tr>
              <td><code>${escapeHtml(m.rep_id)}</code></td>
              <td><strong>${escapeHtml(m.name)}</strong></td>
              <td>${escapeHtml(m.specialty)}</td>
              <td>${m.weekly_capacity} yêu cầu/tuần</td>
              <td>${escapeHtml(m.email || "—")}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  // File Queue Handling
  function renderFileQueue() {
    const countEl = document.getElementById("selected-files-count");
    const listEl = document.getElementById("selected-files-list");
    const runBtn = document.getElementById("btn-run-files");
    countEl.textContent = String(state.queuedFiles.length);
    runBtn.disabled = state.queuedFiles.length === 0;

    if (!state.queuedFiles.length) {
      listEl.innerHTML = `<p class="muted-empty">Chưa chọn file nào. Bạn có thể tải <code>MinhAn_DuLieu_Mau_TongHop.xlsx</code> ở góc phải để thử nghiệm ngay.</p>`;
      return;
    }

    listEl.innerHTML = state.queuedFiles
      .map(
        (item, idx) => `
      <div class="file-item-row">
        <div>
          <div class="file-item-name">${escapeHtml(item.file.name)}</div>
          <div class="file-item-size">${(item.file.size / 1024).toFixed(1)} KB</div>
        </div>
        <select class="input file-role-select" data-idx="${idx}">
          <option value="auto" ${item.role === "auto" ? "selected" : ""}>Tự động nhận diện (Khuyên dùng)</option>
          <option value="requests" ${item.role === "requests" ? "selected" : ""}>Yêu cầu khách hàng</option>
          <option value="catalog" ${item.role === "catalog" ? "selected" : ""}>Sản phẩm, Giá &amp; Tồn kho</option>
          <option value="inventory" ${item.role === "inventory" ? "selected" : ""}>Tồn kho &amp; Thời gian triển khai</option>
          <option value="policy" ${item.role === "policy" ? "selected" : ""}>Chính sách chiết khấu</option>
          <option value="sales_team" ${item.role === "sales_team" ? "selected" : ""}>Nhân viên Kinh doanh</option>
        </select>
        <button class="btn btn-secondary btn-sm remove-file-btn" data-idx="${idx}" type="button">Xoá</button>
      </div>`
      )
      .join("");

    listEl.querySelectorAll(".file-role-select").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        const i = Number(e.target.getAttribute("data-idx"));
        state.queuedFiles[i].role = e.target.value;
      });
    });
    listEl.querySelectorAll(".remove-file-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const i = Number(e.target.getAttribute("data-idx"));
        state.queuedFiles.splice(i, 1);
        renderFileQueue();
      });
    });
  }

  function addFilesToQueue(fileList) {
    for (const file of fileList) {
      const lower = file.name.toLowerCase();
      if (!lower.endsWith(".csv") && !lower.endsWith(".xlsx")) {
        showToast(`Bỏ qua "${file.name}": chỉ hỗ trợ file .csv hoặc .xlsx`, "error");
        continue;
      }
      state.queuedFiles.push({ file, role: "auto" });
    }
    renderFileQueue();
  }

  function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error(`Không đọc được file ${file.name}`));
      reader.readAsDataURL(file);
    });
  }

  function showImportReport(report) {
    const banner = document.getElementById("import-report-banner");
    if (!report || !report.length) {
      banner.classList.add("hidden");
      return;
    }
    const roleLabels = {
      requests: "Yêu cầu khách hàng",
      catalog: "Danh mục Sản phẩm & Giá & Tồn kho",
      inventory: "Tồn kho & Thời gian triển khai",
      policy: "Chính sách chiết khấu",
      sales_team: "Nhân viên Kinh doanh",
    };
    const itemsHtml = report
      .map((r) => `<li><strong>${escapeHtml(r.name)}</strong> → ${escapeHtml(roleLabels[r.role] || r.role)} (${r.rows} dòng)</li>`)
      .join("");
    banner.innerHTML = `<strong>Đã nạp &amp; phân tích dữ liệu thành công:</strong><ul style="margin:4px 0 0;padding-left:18px;">${itemsHtml}</ul>`;
    banner.classList.remove("hidden");
  }

  // LLM Modal
  function openLlmModal() {
    document.getElementById("llm-provider").value = state.llmConfig.provider || "gemini";
    document.getElementById("llm-model").value = state.llmConfig.model || "gemini-2.5-flash";
    document.getElementById("llm-api-key").value = state.llmConfig.api_key || "";
    document.getElementById("llm-base-url").value = state.llmConfig.base_url || "";
    document.getElementById("llm-baseurl-wrap").classList.toggle("hidden", (state.llmConfig.provider || "gemini") === "gemini");
    document.getElementById("llm-test-status").textContent = "";
    document.getElementById("llm-modal").classList.remove("hidden");
  }

  function closeLlmModal() {
    document.getElementById("llm-modal").classList.add("hidden");
  }

  function wireEvents() {
    // Main input tabs
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.getAttribute("data-tab")).classList.add("active");
      });
    });

    // KB subtabs
    document.querySelectorAll(".kb-sub-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".kb-sub-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".kb-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(btn.getAttribute("data-kb")).classList.add("active");
      });
    });

    // Drag & drop + file picker
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files?.length) addFilesToQueue(e.dataTransfer.files);
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files?.length) addFilesToQueue(fileInput.files);
      fileInput.value = "";
    });

    document.getElementById("btn-clear-files").addEventListener("click", () => {
      state.queuedFiles = [];
      renderFileQueue();
    });

    document.getElementById("btn-run-files").addEventListener("click", async () => {
      const btn = document.getElementById("btn-run-files");
      btn.disabled = true;
      btn.textContent = "Đang phân tích...";
      try {
        const filesPayload = [];
        for (const item of state.queuedFiles) {
          const b64 = await readFileAsBase64(item.file);
          filesPayload.push({ filename: item.file.name, role: item.role, content_base64: b64 });
        }
        const replace = document.getElementById("files-replace-mode").checked;
        const res = await apiJson("/api/import/files", {
          method: "POST",
          body: JSON.stringify({ files: filesPayload, replace_requests: replace }),
        });
        setWorkspace(res.state);
        showImportReport(res.import_report);
        showToast("Đã nạp file và chạy xong quy trình AI Agent!", "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = state.queuedFiles.length === 0;
        btn.textContent = "Phân tích & Chạy quy trình AI";
      }
    });

    // Google Sheets
    document.getElementById("btn-add-gsheet-row").addEventListener("click", () => {
      const container = document.getElementById("gsheet-links-container");
      const row = document.createElement("div");
      row.className = "gsheet-row";
      row.innerHTML = `
        <input type="url" class="input gsheet-url-input" placeholder="https://docs.google.com/spreadsheets/d/.../edit" />
        <select class="input gsheet-role-select">
          <option value="auto">Tự động nhận diện các sheet</option>
          <option value="requests">Sheet Yêu cầu khách hàng</option>
          <option value="catalog">Sheet Danh mục Sản phẩm &amp; Giá &amp; Tồn kho</option>
          <option value="inventory">Sheet Tồn kho &amp; Thời gian triển khai</option>
          <option value="policy">Sheet Chính sách chiết khấu</option>
          <option value="sales_team">Sheet Nhân viên Kinh doanh</option>
        </select>
        <button type="button" class="btn btn-secondary btn-sm remove-gs-row">Xoá</button>`;
      row.querySelector(".remove-gs-row").addEventListener("click", () => row.remove());
      container.appendChild(row);
    });

    document.getElementById("btn-run-gsheets").addEventListener("click", async () => {
      const rows = Array.from(document.querySelectorAll("#gsheet-links-container .gsheet-row"));
      const links = rows
        .map((r) => ({
          url: r.querySelector(".gsheet-url-input").value.trim(),
          role: r.querySelector(".gsheet-role-select").value,
        }))
        .filter((x) => x.url);

      if (!links.length) {
        showToast("Vui lòng dán ít nhất 1 link Google Sheets.", "error");
        return;
      }

      const btn = document.getElementById("btn-run-gsheets");
      btn.disabled = true;
      btn.textContent = "Đang tải từ Google Sheets...";
      try {
        const replace = document.getElementById("gsheet-replace-mode").checked;
        const res = await apiJson("/api/import/google-sheets", {
          method: "POST",
          body: JSON.stringify({ links, replace_requests: replace }),
        });
        setWorkspace(res.state);
        showImportReport(res.import_report);
        showToast("Đã kết nối Google Sheets và hoàn tất phân tích!", "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Kết nối Google Sheets & Phân tích";
      }
    });

    // Quick Single Request
    document.querySelectorAll(".chip-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.getAttribute("data-preset");
        if (mode === "complete") {
          document.getElementById("quick-customer").value = "Công ty CP Cơ điện Đại Phát";
          document.getElementById("quick-channel").value = "Email";
          document.getElementById("quick-approver").value = "Ông Nguyễn Mạnh Hùng - Giám đốc";
          document.getElementById("quick-text").value =
            "Chào Minh An, bên Đại Phát cần báo giá 12 Laptop Dell Latitude 5440, 02 Thiết bị tường lửa FortiGate 60F và 01 Gói triển khai & cấu hình hạ tầng mạng LAN văn phòng. Ngân sách tổng 320 triệu đồng, thời hạn triển khai trong 10 ngày. Đề nghị hỗ trợ chiết khấu 10%. Người phê duyệt: Ông Nguyễn Mạnh Hùng - Giám đốc.";
        } else {
          document.getElementById("quick-customer").value = "Công ty TNHH Đầu tư Sao Bắc";
          document.getElementById("quick-channel").value = "Biểu mẫu Web";
          document.getElementById("quick-approver").value = "";
          document.getElementById("quick-text").value =
            "Bên mình cần mua gấp 06 Máy chủ HPE ProLiant DL380 Gen11 giao trong 3 ngày tới, kèm 10 Switch Aruba CX 6100. Chưa chốt ngân sách và chưa rõ sếp nào phê duyệt.";
        }
      });
    });

    document.getElementById("btn-run-quick").addEventListener("click", async () => {
      const btn = document.getElementById("btn-run-quick");
      btn.disabled = true;
      try {
        const res = await apiJson("/api/evaluate-single", {
          method: "POST",
          body: JSON.stringify({
            customer_name: document.getElementById("quick-customer").value,
            channel: document.getElementById("quick-channel").value,
            approver: document.getElementById("quick-approver").value,
            request_text: document.getElementById("quick-text").value,
          }),
        });
        state.stageFilter = "ALL";
        document.getElementById("filter-stage").value = "ALL";
        setWorkspace(res.state, res.created_opportunity.opportunity_id);
        showToast("AI Agent đã xử lý xong yêu cầu mới!", "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    // Knowledge base inline save
    document.getElementById("btn-save-kb").addEventListener("click", async () => {
      const catalog = JSON.parse(JSON.stringify(state.workspace.catalog));
      document.querySelectorAll(".kb-cat-input").forEach((inp) => {
        const idx = Number(inp.getAttribute("data-idx"));
        const field = inp.getAttribute("data-field");
        catalog[idx][field] = Number(inp.value) || 0;
      });
      const policy = JSON.parse(JSON.stringify(state.workspace.policy));
      document.querySelectorAll(".kb-pol-input").forEach((inp) => {
        const idx = Number(inp.getAttribute("data-idx"));
        const field = inp.getAttribute("data-field");
        policy.tiers[idx][field] = Number(inp.value) || 0;
      });
      try {
        const res = await apiJson("/api/knowledge/update", {
          method: "POST",
          body: JSON.stringify({ catalog, policy }),
        });
        setWorkspace(res.state);
        showToast("Đã cập nhật dữ liệu nền và tính toán lại toàn bộ hồ sơ!", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    // Filters
    document.getElementById("search-input").addEventListener("input", (e) => {
      state.searchQuery = e.target.value;
      renderOpportunityList();
    });
    document.getElementById("filter-stage").addEventListener("change", (e) => {
      state.stageFilter = e.target.value;
      document.getElementById("btn-clear-stage-filter").classList.toggle("hidden", state.stageFilter === "ALL");
      renderOpportunityList();
    });
    document.getElementById("btn-clear-stage-filter").addEventListener("click", () => {
      state.stageFilter = "ALL";
      document.getElementById("filter-stage").value = "ALL";
      document.getElementById("btn-clear-stage-filter").classList.add("hidden");
      renderOpportunityList();
    });

    // Load Demo button
    document.getElementById("btn-load-demo").addEventListener("click", async () => {
      try {
        const res = await apiJson("/api/load-demo", { method: "POST", body: "{}" });
        state.stageFilter = "ALL";
        document.getElementById("filter-stage").value = "ALL";
        document.getElementById("import-report-banner").classList.add("hidden");
        setWorkspace(res.state);
        showToast("Đã nạp lại 12 yêu cầu mẫu Công ty Minh An!", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    // LLM Modal events
    document.getElementById("btn-open-llm").addEventListener("click", openLlmModal);
    document.getElementById("btn-close-llm").addEventListener("click", closeLlmModal);
    document.querySelector("#llm-modal .modal-backdrop").addEventListener("click", closeLlmModal);
    document.getElementById("llm-provider").addEventListener("change", (e) => {
      const isGemini = e.target.value === "gemini";
      document.getElementById("llm-baseurl-wrap").classList.toggle("hidden", isGemini);
      if (isGemini && document.getElementById("llm-model").value === "gpt-4o-mini") {
        document.getElementById("llm-model").value = "gemini-2.5-flash";
      } else if (!isGemini && document.getElementById("llm-model").value === "gemini-2.5-flash") {
        document.getElementById("llm-model").value = "gpt-4o-mini";
      }
    });

    document.getElementById("btn-test-llm").addEventListener("click", async () => {
      const statusEl = document.getElementById("llm-test-status");
      statusEl.textContent = "Đang kiểm tra kết nối...";
      try {
        const res = await apiJson("/api/llm/test", {
          method: "POST",
          body: JSON.stringify({
            provider: document.getElementById("llm-provider").value,
            model: document.getElementById("llm-model").value,
            api_key: document.getElementById("llm-api-key").value,
            base_url: document.getElementById("llm-base-url").value,
          }),
        });
        statusEl.textContent = `Kết nối thành công! Phản hồi: ${res.reply}`;
        statusEl.style.color = "var(--green)";
      } catch (err) {
        statusEl.textContent = `Thất bại: ${err.message}`;
        statusEl.style.color = "var(--red)";
      }
    });

    document.getElementById("btn-save-llm").addEventListener("click", () => {
      saveLlmConfig({
        provider: document.getElementById("llm-provider").value,
        model: document.getElementById("llm-model").value.trim(),
        api_key: document.getElementById("llm-api-key").value.trim(),
        base_url: document.getElementById("llm-base-url").value.trim(),
      });
      closeLlmModal();
      showToast("Đã lưu cấu hình LLM trên trình duyệt.", "success");
    });
  }

  async function init() {
    wireEvents();
    try {
      const data = await apiJson("/api/state");
      setWorkspace(data.state);
    } catch (err) {
      showToast(`Không tải được dữ liệu khởi tạo: ${err.message}`, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();

