"""
multi_ai.py
-----------
Dùng Gemini (miễn phí) để phân tích chuyên sâu 1 mã cổ phiếu cho lệnh /scan.
Claude và GPT-4o đã được bỏ khỏi module này để đơn giản hóa.

Phần sentiment tin tức cho báo cáo hằng ngày vẫn dùng Claude
thông qua ai_analyzer.py (tự fallback rule-based nếu không có key).
"""
import json
import logging
import re

import config

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Phan tich ngan gon co phieu {symbol} Viet Nam tu du lieu sau:

{data_block}

Tra loi CHI bang JSON (khong them chu nao):
{{"sentiment":"<tich cuc|tieu cuc|trung tinh>","outlook":"<tang|giam|sideway>","confidence":<1-10>,"key_signal":"<tin hieu chinh 1 cau>","risk":"<rui ro chinh 1 cau>","summary":"<nhan dinh 2 cau tieng Viet>"}}"""


def _build_data_block(symbol: str, technical: dict, deep: dict,
                      news_items: list[dict]) -> str:
    news_text = "\n".join(
        f"- [{n['source']}] {n['title']}" for n in news_items[:6]
    ) if news_items else "Không có tin tức liên quan."

    sr = deep.get("sr", {})
    nearest_support    = sr.get("nearest_support")
    nearest_resistance = sr.get("nearest_resistance")
    sr_text = (
        f"Ho tro gan nhat: {nearest_support:,} d\n"
        f"Khang cu gan nhat: {nearest_resistance:,} d"
    ) if nearest_support and nearest_resistance else "Chua xac dinh duoc ho tro/khang cu"

    return f"""
Gia: {technical['last_close']:,} d | Thay doi: {technical['change_pct']:+.2f}%
RSI(14): {technical['rsi']} ({technical['rsi_state']})
MACD: {deep['macd']['trend']} | {deep['macd']['crossover']}
Stochastic: %K={deep['stoch']['k']} -> {deep['stoch']['state']}
Bollinger: {deep['bb']['position']} | %B={deep['bb']['pct_b']}
ADX(14): {deep['adx']['adx']} -> {deep['adx']['strength']}
MA20: {technical['ma20']:,} d | Xu huong: {technical['ma_trend']}
Volume: {deep['volume']['vol_vs_avg']}
{sr_text}
Ngan han 5 phien: {deep['mtf']['ngan_han_5p']}
Trung han 20 phien: {deep['mtf']['trung_han_20p']}
Dai han 60 phien: {deep['mtf']['dai_han_60p']}

Tin tuc:
{news_text}
""".strip()


def _parse_json_response(raw: str) -> dict | None:
    text = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
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

    import requests as req

    # Dùng HTTP trực tiếp — không cần thư viện google-genai, tránh version conflict
    models_to_try = [
        "gemini-2.0-flash-lite",  # 30 RPM, 1500 RPD - quota cao nhất free tier
        "gemini-2.0-flash",       # 15 RPM, 1500 RPD
        "gemini-2.5-flash-lite",  # 30 RPM, 1500 RPD
    ]
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    for model_name in models_to_try:
        try:
            url = f"{base_url}/{model_name}:generateContent?key={config.GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
            }
            resp = req.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                raw = (data.get("candidates", [{}])[0]
                           .get("content", {})
                           .get("parts", [{}])[0]
                           .get("text", ""))
                result = _parse_json_response(raw)
                if result:
                    logger.info("Gemini OK voi model: %s", model_name)
                    return result
            elif resp.status_code == 429:
                # Rate limit — chờ 5 giây rồi thử model tiếp theo
                logger.warning("Gemini %s: 429 rate limit, cho 5s...", model_name)
                import time
                time.sleep(5)
                continue
            else:
                logger.warning("Gemini %s HTTP %d: %s",
                               model_name, resp.status_code, resp.text[:100])
        except Exception as inner:
            logger.warning("Gemini model %s loi: %s", model_name, str(inner)[:80])
            continue

    # Không dùng _ai_errors dict, chỉ log và return None
    logger.warning("Gemini: Tat ca model deu that bai")
    return None


def analyze_multi_ai(symbol: str, technical: dict, deep: dict,
                     news_items: list[dict]) -> dict:
    """Gọi Gemini phân tích mã, trả về dict kết quả. Không bao giờ raise exception."""
    if not config.GEMINI_API_KEY:
        return {
            "available_ais": [],
            "gemini_result": None,
            "error": "Chua co GEMINI_API_KEY — lay key mien phi tai aistudio.google.com",
        }

    try:
        data_block = _build_data_block(symbol, technical, deep, news_items)
        prompt = ANALYSIS_PROMPT.format(symbol=symbol, data_block=data_block)
        result = _call_gemini(prompt)
    except Exception as e:
        logger.warning("analyze_multi_ai loi bat ngo: %s", e)
        result = None

    if result:
        return {
            "available_ais": ["Gemini"],
            "gemini_result": result,
            "error": None,
        }
    else:
        return {
            "available_ais": [],
            "gemini_result": None,
            "error": "Gemini khong phan hoi (429 quota / loi mang) — thu lai sau.",
        }


def format_multi_ai_block(synthesis: dict) -> str:
    """Format kết quả Gemini thành đoạn Markdown cho Telegram."""
    if not synthesis.get("available_ais"):
        err = synthesis.get("error", "Khong co AI nao phan hoi")
        return f"🤖 *NHAN DINH AI (Gemini)*\n_{err}_"

    result = synthesis.get("gemini_result", {})
    if not result:
        return "🤖 *NHAN DINH AI (Gemini)*\n_Khong lay duoc ket qua._"

    outlook_icon = {
        "tang": "🟢", "giam": "🔴", "sideway": "🟡"
    }.get(result.get("outlook", ""), "⚪")

    conf = result.get("confidence", 0)
    conf_label = (
        "rat cao" if conf >= 8 else
        "cao"     if conf >= 6 else
        "trung binh" if conf >= 4 else
        "thap"
    )

    lines = [
        "🤖 *NHAN DINH AI — Gemini*",
        f"{outlook_icon} Xu huong: *{result.get('outlook', '?').upper()}* | "
        f"Sentiment: {result.get('sentiment', '?')} | "
        f"Do tin cay: {conf}/10 ({conf_label})",
        "",
        f"_{result.get('summary', '')}_",
        "",
        f"• Tin hieu chinh: {result.get('key_signal', '')}",
        f"• Rui ro can chu y: {result.get('risk', '')}",
    ]
    return "\n".join(lines)
