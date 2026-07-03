"""
market_summary_ai.py
---------------------
Dùng Gemini (miễn phí) để tổng hợp nhận định thị trường chung
cho phần cuối báo cáo hằng ngày. Gọi 1 lần duy nhất cho cả watchlist.
"""
import json
import logging
import re

import config

logger = logging.getLogger(__name__)

MARKET_PROMPT = """Ban la chuyen gia phan tich thi truong chung khoan Viet Nam.
Duoi day la tom tat ket qua phan tich ky thuat toan bo watchlist phien {period}:

{summary_block}

Dua vao du lieu tren, hay dua ra nhan dinh thi truong ngan gon.
Tra loi CHI bang JSON, khong them chu nao khac:
{{
  "market_mood": <"tich cuc" | "tieu cuc" | "trung tinh" | "hon hop">,
  "confidence": <1-10>,
  "highlight": "<ma hoac nhom nganh noi bat nhat can chu y, 1 cau>",
  "opportunity": "<co hoi lon nhat trong phien, 1 cau>",
  "risk": "<rui ro chinh can than trong, 1 cau>",
  "action": "<khuyen nghi hanh dong tong the va ly do ngan gon>"
}}"""


def _build_summary_block(results: list[dict]) -> str:
    n = len(results)
    if not n:
        return ""
    breakout  = [r["symbol"] for r in results if r["technical"]["breakout"]["is_breakout"]]
    high_prob = [r["symbol"] for r in results if r["prediction"]["probability_up_pct"] >= 65]
    low_prob  = [r["symbol"] for r in results if r["prediction"]["probability_up_pct"] <= 35]
    uptrend   = [r["symbol"] for r in results if r["technical"]["ma_trend"] == "tang"]
    downtrend = [r["symbol"] for r in results if r["technical"]["ma_trend"] == "giam"]
    avg_prob  = round(sum(r["prediction"]["probability_up_pct"] for r in results) / n, 1)

    lines = [
        f"Tong so ma theo doi: {n}",
        f"Xac suat tang gia trung binh: {avg_prob}%",
        f"Xu huong tang (MA20): {len(uptrend)}/{n} ma — {', '.join(uptrend) or 'khong co'}",
        f"Xu huong giam (MA20): {len(downtrend)}/{n} ma — {', '.join(downtrend) or 'khong co'}",
        f"Breakout hom nay: {', '.join(breakout) or 'khong co'}",
        f"Xac suat tang cao (>=65%): {', '.join(high_prob) or 'khong co'}",
        f"Xac suat giam cao (<=35%): {', '.join(low_prob) or 'khong co'}",
        "\nChi tiet tung ma:",
    ]
    for r in results:
        t, p = r["technical"], r["prediction"]
        lines.append(
            f"  {r['symbol']}: gia {t['last_close']:,.0f}d ({t['change_pct']:+.1f}%) | "
            f"RSI={t['rsi']} | MA={t['ma_trend']} | XS tang={p['probability_up_pct']}%"
        )
    return "\n".join(lines)


def _parse(raw: str) -> dict | None:
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


def _call_gemini(prompt: str) -> dict | None:
    if not config.GEMINI_API_KEY:
        return None
    models_to_try = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    try:
        from google import genai
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                result = _parse(response.text or "")
                if result:
                    return result
            except Exception:
                continue
        return None
    except Exception as e:
        logger.warning("Gemini market summary loi: %s", e)
        return None


def get_market_summary(results: list[dict], period_label: str) -> str:
    if not results:
        return ""
    if not config.GEMINI_API_KEY:
        return _rule_based_summary(results)

    summary_block = _build_summary_block(results)
    prompt = MARKET_PROMPT.format(period=period_label, summary_block=summary_block)
    result = _call_gemini(prompt)

    if not result:
        return _rule_based_summary(results)

    mood_icon = {
        "tich cuc": "🟢", "tieu cuc": "🔴",
        "trung tinh": "🟡", "hon hop": "🟠"
    }.get(result.get("market_mood", ""), "⚪")

    conf = result.get("confidence", 0)
    lines = [
        "─" * 30,
        "🌐 *NHAN DINH THI TRUONG — Gemini AI*",
        f"{mood_icon} Tam ly chung: *{result.get('market_mood','?').upper()}* | "
        f"Do tin cay: {conf}/10",
        "",
        f"📌 *Noi bat:* {result.get('highlight', '')}",
        f"💡 *Co hoi:* {result.get('opportunity', '')}",
        f"⚠️ *Rui ro:* {result.get('risk', '')}",
        "",
        f"🎯 *Khuyen nghi:* {result.get('action', '')}",
    ]
    return "\n".join(lines)


def _rule_based_summary(results: list[dict]) -> str:
    n = len(results)
    if not n:
        return ""
    uptrend   = sum(1 for r in results if r["technical"]["ma_trend"] == "tang")
    breakouts = [r["symbol"] for r in results if r["technical"]["breakout"]["is_breakout"]]
    avg_prob  = round(sum(r["prediction"]["probability_up_pct"] for r in results) / n, 1)
    mood      = "tich cuc" if uptrend > n * 0.6 else "tieu cuc" if uptrend < n * 0.4 else "trung tinh"
    icon      = {"tich cuc": "🟢", "tieu cuc": "🔴", "trung tinh": "🟡"}.get(mood, "🟡")
    lines = [
        "─" * 30,
        "🌐 *TONG KET THI TRUONG*",
        f"{icon} Tam ly chung: *{mood.upper()}*",
        f"• {uptrend}/{n} ma dang trong xu huong tang (MA20)",
        f"• Xac suat tang gia trung binh: {avg_prob}%",
    ]
    if breakouts:
        lines.append(f"• Ma breakout: {', '.join(breakouts)}")
    return "\n".join(lines)
