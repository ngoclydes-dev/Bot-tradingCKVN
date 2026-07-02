"""
market_summary_ai.py
---------------------
Tổng hợp nhận định thị trường chung từ 3 AI (Claude, GPT-4o, Gemini)
cho phần cuối báo cáo hằng ngày.

Khác với deep_analysis.py (phân tích từng mã riêng lẻ), module này
nhận vào TÓM TẮT kết quả toàn bộ watchlist và yêu cầu 3 AI đưa ra:
  1. Nhận định thị trường chung hôm nay
  2. Nhóm/mã nổi bật cần chú ý
  3. Rủi ro/cơ hội lớn nhất trong phiên

Chỉ gọi API 1 lần / 3 AI (không nhân với số mã) nên rất nhanh,
phù hợp đưa vào cuối báo cáo tự động 8h/13h hằng ngày.
"""
import logging
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

logger = logging.getLogger(__name__)

AI_TIMEOUT = 20

MARKET_PROMPT = """Bạn là chuyên gia phân tích thị trường chứng khoán Việt Nam.
Dưới đây là tóm tắt kết quả phân tích kỹ thuật toàn bộ watchlist trong phiên {period}:

{summary_block}

Dựa vào dữ liệu trên, hãy đưa ra nhận định thị trường ngắn gọn.
Trả lời CHỈ bằng JSON, không thêm chữ nào khác:
{{
  "market_mood": <"tích cực" | "tiêu cực" | "trung tính" | "hỗn hợp">,
  "confidence": <1-10>,
  "highlight": "<mã hoặc nhóm ngành nổi bật nhất cần chú ý, 1 câu>",
  "opportunity": "<cơ hội lớn nhất trong phiên, 1 câu>",
  "risk": "<rủi ro chính cần thận trọng, 1 câu>",
  "action": "<khuyến nghị hành động tổng thể: mua/bán/chờ/quan sát, và lý do ngắn gọn>"
}}"""


def _build_summary_block(results: list[dict]) -> str:
    """Tóm tắt toàn bộ watchlist thành 1 đoạn text ngắn gọn cho AI đọc."""
    lines = []
    breakout = [r["symbol"] for r in results if r["technical"]["breakout"]["is_breakout"]]
    high_prob = [r["symbol"] for r in results if r["prediction"]["probability_up_pct"] >= 65]
    low_prob  = [r["symbol"] for r in results if r["prediction"]["probability_up_pct"] <= 35]
    overbought = [r["symbol"] for r in results if r["technical"]["rsi"] >= config.RSI_OVERBOUGHT]
    oversold   = [r["symbol"] for r in results if r["technical"]["rsi"] <= config.RSI_OVERSOLD]
    uptrend    = [r["symbol"] for r in results if r["technical"]["ma_trend"] == "tăng"]
    downtrend  = [r["symbol"] for r in results if r["technical"]["ma_trend"] == "giảm"]

    # Tỷ lệ tổng quan
    n = len(results)
    avg_prob = round(sum(r["prediction"]["probability_up_pct"] for r in results) / n, 1) if n else 50

    lines.append(f"Tổng số mã theo dõi: {n}")
    lines.append(f"Xác suất tăng giá trung bình: {avg_prob}%")
    lines.append(f"Xu hướng tăng (MA20): {len(uptrend)}/{n} mã — {', '.join(uptrend) if uptrend else 'không có'}")
    lines.append(f"Xu hướng giảm (MA20): {len(downtrend)}/{n} mã — {', '.join(downtrend) if downtrend else 'không có'}")
    lines.append(f"Breakout hôm nay: {', '.join(breakout) if breakout else 'không có'}")
    lines.append(f"Xác suất tăng cao (≥65%): {', '.join(high_prob) if high_prob else 'không có'}")
    lines.append(f"Xác suất giảm cao (≤35%): {', '.join(low_prob) if low_prob else 'không có'}")
    lines.append(f"RSI quá mua (≥{config.RSI_OVERBOUGHT}): {', '.join(overbought) if overbought else 'không có'}")
    lines.append(f"RSI quá bán (≤{config.RSI_OVERSOLD}): {', '.join(oversold) if oversold else 'không có'}")

    # Chi tiết từng mã (ngắn gọn)
    lines.append("\nChi tiết từng mã:")
    for r in results:
        t = r["technical"]
        p = r["prediction"]
        lines.append(
            f"  {r['symbol']}: giá {t['last_close']:,.0f}đ ({t['change_pct']:+.1f}%) | "
            f"RSI={t['rsi']} | MA={t['ma_trend']} | "
            f"Xác suất tăng={p['probability_up_pct']}%"
        )
    return "\n".join(lines)


def _parse_response(raw: str) -> dict | None:
    text = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


def _call_claude(prompt: str) -> dict | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_response("".join(b.text for b in resp.content if b.type == "text"))
    except Exception as e:
        logger.warning("Claude market summary lỗi: %s", e)
        return None


def _call_gpt(prompt: str) -> dict | None:
    if not config.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        return _parse_response(resp.choices[0].message.content or "")
    except Exception as e:
        logger.warning("GPT market summary lỗi: %s", e)
        return None


def _call_gemini(prompt: str) -> dict | None:
    if not config.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        resp = model.generate_content(prompt)
        return _parse_response(resp.text or "")
    except Exception as e:
        logger.warning("Gemini market summary lỗi: %s", e)
        return None


def get_market_summary(results: list[dict], period_label: str) -> str:
    """
    Gọi 3 AI song song, tổng hợp nhận định thị trường.
    results: list kết quả từ analyze_one_symbol() trong main.py
    Trả về chuỗi Markdown sẵn sàng gửi Telegram.
    """
    if not results:
        return ""

    # Kiểm tra AI nào có key
    active = {}
    if config.ANTHROPIC_API_KEY: active["Claude"]  = _call_claude
    if config.OPENAI_API_KEY:    active["GPT-4o"]  = _call_gpt
    if config.GEMINI_API_KEY:    active["Gemini"]  = _call_gemini

    if not active:
        # Không có AI nào — dùng rule-based đơn giản
        return _rule_based_summary(results)

    summary_block = _build_summary_block(results)
    prompt = MARKET_PROMPT.format(
        period=period_label,
        summary_block=summary_block,
    )

    # Gọi song song
    ai_results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=len(active)) as executor:
        futures = {executor.submit(fn, prompt): name for name, fn in active.items()}
        for future in as_completed(futures, timeout=AI_TIMEOUT + 5):
            name = futures[future]
            try:
                ai_results[name] = future.result(timeout=AI_TIMEOUT)
            except Exception as e:
                logger.warning("%s timeout/lỗi: %s", name, e)
                ai_results[name] = None

    valid = {k: v for k, v in ai_results.items() if v}
    if not valid:
        return _rule_based_summary(results)

    return _format_market_summary(valid, results)


def _format_market_summary(valid: dict[str, dict], results: list[dict]) -> str:
    """Format kết quả 3 AI thành khối tổng kết thị trường."""

    # Tính đồng thuận
    moods = [r["market_mood"] for r in valid.values() if "market_mood" in r]
    mood_counts = {m: moods.count(m) for m in set(moods)}
    consensus_mood = max(mood_counts, key=mood_counts.get) if moods else "trung tính"
    confs = [r["confidence"] for r in valid.values()
             if "confidence" in r and isinstance(r["confidence"], (int, float))]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else 0
    n_valid = len(valid)
    max_agree = max(mood_counts.values()) if mood_counts else 0

    # Icon tâm lý thị trường
    mood_icon = {
        "tích cực": "🟢", "tiêu cực": "🔴",
        "trung tính": "🟡", "hỗn hợp": "🟠"
    }.get(consensus_mood, "⚪")

    agree_text = (
        f"đồng thuận ({n_valid}/{n_valid})" if max_agree == n_valid else
        f"đa số ({max_agree}/{n_valid})"    if max_agree > 1 else
        f"bất đồng ({n_valid} AI khác nhau)"
    )

    lines = [
        "─" * 30,
        f"🌐 *NHẬN ĐỊNH THỊ TRƯỜNG — ĐA AI*",
        f"AI tham gia: {' • '.join(valid.keys())}",
        f"{mood_icon} Tâm lý chung: *{consensus_mood.upper()}* ({agree_text})",
        f"Độ tin cậy TB: {avg_conf}/10",
        "",
    ]

    # Tổng hợp các điểm đồng thuận
    highlights  = [r.get("highlight",  "") for r in valid.values() if r.get("highlight")]
    opps        = [r.get("opportunity","") for r in valid.values() if r.get("opportunity")]
    risks       = [r.get("risk",       "") for r in valid.values() if r.get("risk")]
    actions     = [r.get("action",     "") for r in valid.values() if r.get("action")]

    if highlights:
        lines.append(f"📌 *Nổi bật:* {highlights[0]}")
    if opps:
        lines.append(f"💡 *Cơ hội:* {opps[0]}")
    if risks:
        lines.append(f"⚠️ *Rủi ro:* {risks[0]}")

    lines.append("")

    # Khuyến nghị từng AI
    for name, result in valid.items():
        if not result or not result.get("action"):
            continue
        emoji = {"Claude": "🟣", "GPT-4o": "🟢", "Gemini": "🔵"}.get(name, "⚪")
        lines.append(f"{emoji} *{name}:* {result['action']}")

    return "\n".join(lines)


def _rule_based_summary(results: list[dict]) -> str:
    """Fallback không cần AI — tổng kết thống kê đơn giản."""
    n = len(results)
    if not n:
        return ""

    uptrend   = sum(1 for r in results if r["technical"]["ma_trend"] == "tăng")
    breakouts = [r["symbol"] for r in results if r["technical"]["breakout"]["is_breakout"]]
    avg_prob  = round(sum(r["prediction"]["probability_up_pct"] for r in results) / n, 1)

    mood = "tích cực" if uptrend > n * 0.6 else "tiêu cực" if uptrend < n * 0.4 else "trung tính"
    mood_icon = {"tích cực": "🟢", "tiêu cực": "🔴", "trung tính": "🟡"}.get(mood, "🟡")

    lines = [
        "─" * 30,
        f"🌐 *TỔNG KẾT THỊ TRƯỜNG*",
        f"{mood_icon} Tâm lý chung: *{mood.upper()}*",
        f"• {uptrend}/{n} mã đang trong xu hướng tăng (MA20)",
        f"• Xác suất tăng giá TB toàn watchlist: {avg_prob}%",
    ]
    if breakouts:
        lines.append(f"• Mã breakout: {', '.join(breakouts)}")

    return "\n".join(lines)
