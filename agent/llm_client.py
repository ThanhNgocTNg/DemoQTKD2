"""Optional LLM integration (Gemini or OpenAI-compatible) using pure standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def test_llm_connection(provider: str, api_key: str, model: str, base_url: str = "") -> Dict[str, Any]:
    """Verify optional LLM credentials with a tiny prompt."""
    if not api_key.strip():
        return {"ok": False, "error": "Chưa nhập API Key."}

    prompt = "Trả lời đúng 1 từ: OK"
    try:
        reply = call_llm_text(provider, api_key, model, prompt, base_url=base_url, timeout=12)
        return {"ok": True, "reply": reply[:80]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def call_llm_text(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    base_url: str = "",
    timeout: int = 25,
) -> str:
    """Call Gemini REST API or OpenAI-compatible Chat Completions endpoint."""
    prov = (provider or "gemini").lower().strip()

    if prov == "gemini":
        chosen_model = model.strip() or "gemini-2.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{chosen_model}:generateContent?key={api_key.strip()}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        candidates = body.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini không trả về nội dung.")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip()

    # OpenAI-compatible
    endpoint = (base_url.strip().rstrip("/") or "https://api.openai.com/v1") + "/chat/completions"
    chosen_model = model.strip() or "gpt-4o-mini"
    payload = {
        "model": chosen_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Bạn là AI Agent hỗ trợ bán hàng B2B cho Công ty Minh An. Trả lời bằng tiếng Việt chuyên nghiệp, ngắn gọn, chính xác."},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key.strip()}",
    }
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def refine_customer_draft_with_llm(
    opp: Dict[str, Any],
    llm_config: Optional[Dict[str, str]],
) -> Optional[str]:
    """Use configured LLM to polish the customer email draft while preserving exact numbers."""
    if not llm_config or not llm_config.get("api_key"):
        return None

    prompt = (
        "Hãy viết lại bản nháp email phản hồi khách hàng B2B dưới đây cho Công ty Minh An sao cho "
        "lịch sự, chuyên nghiệp và thuyết phục hơn bằng tiếng Việt. "
        "BẮT BUỘC giữ nguyên toàn bộ mã sản phẩm, số lượng, đơn giá, tổng tiền, % chiết khấu, thời gian giao hàng và tên người phụ trách:\n\n"
        f"{opp.get('customer_response_draft', '')}"
    )
    return call_llm_text(
        provider=llm_config.get("provider", "gemini"),
        api_key=llm_config.get("api_key", ""),
        model=llm_config.get("model", ""),
        prompt=prompt,
        base_url=llm_config.get("base_url", ""),
    )

