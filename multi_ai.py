"""
multi_ai.py
-----------
Gọi đồng thời 3 AI (Claude, GPT-4o, Gemini) để phân tích cùng 1 mã
cổ phiếu, sau đó tổng hợp thành 1 nhận định cuối cùng.

Thiết kế:
  - Mỗi AI nhận đúng cùng 1 prompt dữ liệu kỹ thuật + tin tức
  - Trả về JSON chuẩn: {sentiment, outlook, key_signal, risk, confidence}
  - Module này tổng hợp: đếm đa số, tính điểm trung bình, highlight
    điểm đồng thuận và điểm bất đồng giữa 3 AI
  - Nếu 1 hoặc 2 AI lỗi/không có key → vẫn chạy với AI còn lại,
    không crash toàn bộ

Cách bật từng AI:
  - Claude:  khai báo ANTHROPIC_API_KEY trong GitHub Secrets + .env
  - GPT-4o:  khai báo OPENAI_API_KEY
  - Gemini:  khai báo GEMINI_API_KEY
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import config

logger = logging.getLogger(__name__)

# Timeout (giây) cho mỗi lần gọi AI — tránh 1 AI chậm làm kẹt cả bot
AI_TIMEOUT = 25

# Prompt chuẩn gửi cho mỗi AI (giống nhau để so sánh công bằng)
ANALYSIS_PROMPT = """Bạn là chuyên gia phân tích chứng khoán Việt Nam.
Dưới đây là dữ liệu kỹ thuật và tin tức của mã {symbol}:

{data_block}

Hãy phân tích và trả lời CHỈ bằng JSON (không thêm bất kỳ chữ nào khác):
{{
  "sentiment": <"tích cực" | "tiêu cực" | "trung tính">,
  "outlook": <"tăng" | "giảm" | "sideway">,
  "confidence": <số 1-10, mức độ chắc chắn của nhận định>,
  "key_signal": "<tín hiệu kỹ thuật quan trọng nhất trong 1 câu>",
  "risk": "<rủi ro chính cần chú ý trong 1 câu>",
  "summary": "<nhận định tổng hợp trong 2-3 câu tiếng Việt>"
}}"""


def _build_data_block(symbol: str, technical: dict, deep: dict,
                      news_items: list[dict]) -> str:
    """Tạo đoạn dữ liệu chuẩn gửi cho mỗi AI."""
    news_text = "\n".join(
        f"- [{n['source']}] {n['title']}" for n in news_items[:6]
    ) if news_items else "Không có tin tức liên quan."

    sr = deep.get('sr', {})
    nearest_support    = sr.get('nearest_support')
    nearest_resistance = sr.get('nearest_resistance')
    sr_text = (
        f"Hỗ trợ gần nhất: {nearest_support:,} đ\n"
        f"Kháng cự gần nhất: {nearest_resistance:,} đ"
    ) if nearest_support and nearest_resistance else "Chưa xác định được hỗ trợ/kháng cự"

    return f"""
Giá: {technical['last_close']:,} đ | Thay đổi: {technical['change_pct']:+.2f}%
RSI(14): {technical['rsi']} ({technical['rsi_state']})
MACD: {deep['macd']['trend']} | {deep['macd']['crossover']}
Stochastic: %K={deep['stoch']['k']} → {deep['stoch']['state']}
Bollinger: {deep['bb']['position']} | %B={deep['bb']['pct_b']}
ADX(14): {deep['adx']['adx']} → {deep['adx']['strength']}
MA20: {technical['ma20']:,} đ | Xu hướng: {technical['ma_trend']}
Volume: {deep['volume']['vol_vs_avg']}
{sr_text}
Ngắn hạn 5 phiên: {deep['mtf']['ngan_han_5p']}
Trung hạn 20 phiên: {deep['mtf']['trung_han_20p']}
Dài hạn 60 phiên: {deep['mtf']['dai_han_60p']}

Tin tức:
{news_text}
""".strip()


def _parse_json_response(raw: str) -> dict | None:
    """Parse JSON từ response AI, bỏ qua markdown code fences nếu có."""
    text = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Thử tìm JSON trong chuỗi nếu có text thừa
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


# ===================== GỌI TỪNG AI =====================


# Lưu lý do lỗi của từng AI để hiển thị trong báo cáo
_ai_errors: dict[str, str] = {}


def _call_claude(prompt: str) -> dict | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in resp.content if b.type == "text")
        return _parse_json_response(raw)
    except Exception as e:
        err = str(e)
        if any(w in err.lower() for w in ["credit", "billing", "payment", "quota", "insufficient"]):
            _ai_errors["Claude"] = "hết credit — cần nạp tiền tại console.anthropic.com"
        else:
            _ai_errors["Claude"] = f"lỗi: {err[:80]}"
        logger.warning("Claude: %s", err)
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
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        return _parse_json_response(raw)
    except Exception as e:
        err = str(e)
        if any(w in err.lower() for w in ["quota", "billing", "insufficient", "exceeded"]):
            _ai_errors["GPT-4o"] = "hết quota — free credit đã hết hạn hoặc cần nạp tiền"
        else:
            _ai_errors["GPT-4o"] = f"lỗi: {err[:80]}"
        logger.warning("GPT: %s", err)
        return None


def _call_gemini(prompt: str) -> dict | None:
    if not config.GEMINI_API_KEY:
        return None
    # Danh sách model thử lần lượt nếu model trước lỗi
    models_to_try = [
        config.GEMINI_MODEL,
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-pro",
    ]
    # Bỏ duplicate giữ thứ tự
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                resp  = model.generate_content(prompt)
                raw   = resp.text or ""
                result = _parse_json_response(raw)
                if result:
                    logger.info("Gemini OK với model: %s", model_name)
                    return result
            except Exception as inner:
                logger.warning("Gemini model %s lỗi: %s — thử model tiếp theo...", model_name, inner)
                continue
        _ai_errors["Gemini"] = "Tất cả model đều lỗi — kiểm tra API key hoặc quota"
        return None
    except Exception as e:
        _ai_errors["Gemini"] = f"lỗi: {str(e)[:80]}"
        logger.warning("Gemini: %s", e)
        return None


# ===================== TỔNG HỢP KẾT QUẢ =====================

def _synthesize(results: dict[str, dict | None]) -> dict:
    """
    Tổng hợp kết quả từ nhiều AI thành 1 nhận định cuối cùng.
    results = {"Claude": {...}, "GPT-4o": {...}, "Gemini": {...}}
    """
    valid = {name: r for name, r in results.items() if r is not None}

    if not valid:
        return {
            "available_ais": [],
            "consensus_outlook": "không xác định",
            "consensus_sentiment": "trung tính",
            "avg_confidence": 0,
            "agreement_level": "không có AI nào phản hồi",
            "individual": {},
            "synthesis": "Không có AI nào phản hồi được — kiểm tra lại API keys.",
        }

    # Đếm đa số outlook
    outlooks   = [r["outlook"]   for r in valid.values() if "outlook"   in r]
    sentiments = [r["sentiment"] for r in valid.values() if "sentiment" in r]
    confs      = [r["confidence"] for r in valid.values()
                  if "confidence" in r and isinstance(r["confidence"], (int, float))]

    outlook_counts   = {o: outlooks.count(o)   for o in set(outlooks)}
    sentiment_counts = {s: sentiments.count(s) for s in set(sentiments)}

    consensus_outlook   = max(outlook_counts,   key=outlook_counts.get)   if outlooks   else "không rõ"
    consensus_sentiment = max(sentiment_counts, key=sentiment_counts.get) if sentiments else "trung tính"
    avg_confidence      = round(sum(confs) / len(confs), 1)               if confs      else 0

    # Mức độ đồng thuận
    n_valid = len(valid)
    max_agreement = max(outlook_counts.values()) if outlook_counts else 0
    if n_valid == 1:
        agreement = "chỉ có 1 AI"
    elif max_agreement == n_valid:
        agreement = f"đồng thuận hoàn toàn ({n_valid}/{n_valid} AI)"
    elif max_agreement == n_valid - 1:
        agreement = f"đa số đồng thuận ({max_agreement}/{n_valid} AI)"
    else:
        agreement = f"bất đồng ({n_valid} AI khác nhau)"

    # Tổng hợp summary từ tất cả AI
    summaries = [
        f"*{name}:* {r.get('summary', '')}"
        for name, r in valid.items() if r.get("summary")
    ]

    return {
        "available_ais":      list(valid.keys()),
        "consensus_outlook":  consensus_outlook,
        "consensus_sentiment": consensus_sentiment,
        "avg_confidence":     avg_confidence,
        "agreement_level":    agreement,
        "individual":         valid,
        "synthesis":          "\n\n".join(summaries),
    }


# ===================== HÀM CHÍNH =====================

def analyze_multi_ai(symbol: str, technical: dict, deep: dict,
                     news_items: list[dict]) -> dict:
    """
    Gọi 3 AI song song (dùng ThreadPoolExecutor), timeout sau AI_TIMEOUT giây.
    Trả về dict tổng hợp sẵn sàng để format thành tin nhắn Telegram.
    """
    data_block = _build_data_block(symbol, technical, deep, news_items)
    prompt     = ANALYSIS_PROMPT.format(symbol=symbol, data_block=data_block)

    ai_functions = {
        "Claude":  lambda: _call_claude(prompt),
        "GPT-4o":  lambda: _call_gpt(prompt),
        "Gemini":  lambda: _call_gemini(prompt),
    }

    # Chỉ gọi AI đã có key
    active = {
        name: fn for name, fn in ai_functions.items()
        if (name == "Claude"  and config.ANTHROPIC_API_KEY) or
           (name == "GPT-4o"  and config.OPENAI_API_KEY)   or
           (name == "Gemini"  and config.GEMINI_API_KEY)
    }

    if not active:
        logger.warning("Không có API key nào được cấu hình cho multi-AI analysis.")
        return _synthesize({})

    results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=len(active)) as executor:
        futures = {executor.submit(fn): name for name, fn in active.items()}
        for future in as_completed(futures, timeout=AI_TIMEOUT + 5):
            name = futures[future]
            try:
                results[name] = future.result(timeout=AI_TIMEOUT)
                logger.info("%s phân tích xong.", name)
            except TimeoutError:
                logger.warning("%s timeout sau %ds.", name, AI_TIMEOUT)
                results[name] = None
            except Exception as e:
                logger.warning("%s lỗi: %s", name, e)
                results[name] = None

    return _synthesize(results)


def format_multi_ai_block(synthesis: dict) -> str:
    """Format kết quả tổng hợp 3 AI thành đoạn Markdown cho Telegram."""
    if not synthesis["available_ais"]:
        # Hiển thị lý do cụ thể từng AI thất bại
        lines = ["🤖 *NHẬN ĐỊNH ĐA AI*"]
        has_key = []
        no_key  = []
        if config.ANTHROPIC_API_KEY: has_key.append("Claude")
        else: no_key.append("Claude")
        if config.OPENAI_API_KEY: has_key.append("GPT-4o")
        else: no_key.append("GPT-4o")
        if config.GEMINI_API_KEY: has_key.append("Gemini")
        else: no_key.append("Gemini")

        if no_key:
            lines.append(f"_Chưa có key: {', '.join(no_key)}_")
        if has_key:
            lines.append(f"_Có key nhưng gọi API thất bại: {', '.join(has_key)}_")
            for name in has_key:
                if name in _ai_errors:
                    lines.append(f"  • {name}: {_ai_errors[name]}")
        if not has_key and not no_key:
            lines.append("_Chưa thêm API key nào vào GitHub Secrets._")
        return "\n".join(lines)

    # Icon outlook
    outlook_icon = {
        "tăng": "🟢", "giảm": "🔴", "sideway": "🟡"
    }.get(synthesis["consensus_outlook"], "⚪")

    # Mức độ tin cậy
    conf = synthesis["avg_confidence"]
    conf_label = (
        "rất cao" if conf >= 8 else
        "cao"     if conf >= 6 else
        "trung bình" if conf >= 4 else
        "thấp"
    )

    lines = [
        "🤖 *NHẬN ĐỊNH ĐA AI*",
        f"AI tham gia: {' • '.join(synthesis['available_ais'])}",
        f"{outlook_icon} Đồng thuận: *{synthesis['consensus_outlook'].upper()}* "
        f"({synthesis['agreement_level']})",
        f"📊 Sentiment: {synthesis['consensus_sentiment']} | "
        f"Độ tin cậy TB: {conf}/10 ({conf_label})",
        "",
    ]

    # Nhận định từng AI
    for name, result in synthesis["individual"].items():
        if not result:
            continue
        emoji = {"Claude": "🟣", "GPT-4o": "🟢", "Gemini": "🔵"}.get(name, "⚪")
        lines.append(f"{emoji} *{name}* (tin cậy: {result.get('confidence', '?')}/10)")
        if result.get("summary"):
            lines.append(f"_{result['summary']}_")
        if result.get("key_signal"):
            lines.append(f"• Tín hiệu: {result['key_signal']}")
        if result.get("risk"):
            lines.append(f"• Rủi ro: {result['risk']}")
        lines.append("")

    return "\n".join(lines).strip()
