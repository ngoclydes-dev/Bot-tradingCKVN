"""
ai_analyzer.py
--------------
Hai việc chính:
1. analyze_news_sentiment(): dùng Claude (Anthropic API) để đọc các tin
   tức liên quan tới 1 mã và chấm điểm sentiment (-1..+1) + tóm tắt ngắn.
   Nếu không có ANTHROPIC_API_KEY, tự động fallback sang chấm điểm
   rule-based bằng từ khoá tích cực/tiêu cực (bot vẫn chạy được, chỉ
   kém chính xác hơn).
2. predict_probability(): tổng hợp điểm kỹ thuật (RSI, MA trend,
   breakout) + điểm sentiment tin tức thành 1 xác suất tăng giá (0-100%)
   theo trọng số cấu hình trong config.WEIGHTS.

Đây KHÔNG phải là dự báo tài chính được kiểm chứng khoa học, mà là một
chỉ số heuristic tổng hợp tín hiệu - nên dùng làm tham khảo, không phải
khuyến nghị đầu tư.
"""
import json
import logging
import re

import config

logger = logging.getLogger(__name__)

_POSITIVE_KEYWORDS = [
    "tăng trưởng", "lợi nhuận tăng", "vượt kế hoạch", "khả quan", "tích cực",
    "bứt phá", "kỷ lục", "mua vào", "khuyến nghị mua", "nâng giá mục tiêu",
    "lãi", "tăng vốn", "cổ tức cao", "ký hợp đồng", "trúng thầu",
]
_NEGATIVE_KEYWORDS = [
    "giảm lợi nhuận", "thua lỗ", "lỗ", "bán ròng", "khuyến nghị bán",
    "hạ giá mục tiêu", "tiêu cực", "rủi ro", "nợ xấu", "điều tra",
    "xử phạt", "sai phạm", "bán giải chấp", "force sell",
]


def _rule_based_sentiment(news_items: list[dict]) -> dict:
    """Fallback không cần AI: chấm điểm theo từ khoá xuất hiện trong tin."""
    if not news_items:
        return {"score": 0.0, "summary": "Không có tin tức liên quan trong khoảng thời gian theo dõi."}

    score = 0
    hits = []
    for item in news_items:
        text = f"{item['title']} {item['summary']}".lower()
        for kw in _POSITIVE_KEYWORDS:
            if kw in text:
                score += 1
                hits.append(f"+ {kw}")
        for kw in _NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 1
                hits.append(f"- {kw}")

    normalized = max(-1.0, min(1.0, score / max(len(news_items), 1)))
    summary = (
        f"Phân tích rule-based trên {len(news_items)} tin. "
        f"Từ khoá nổi bật: {', '.join(hits[:5]) if hits else 'không có tín hiệu rõ ràng'}."
    )
    return {"score": round(normalized, 2), "summary": summary}


def analyze_news_sentiment(symbol: str, news_items: list[dict]) -> dict:
    """
    Trả về {"score": float -1..1, "summary": str}
    score > 0: tin tức nghiêng tích cực | score < 0: nghiêng tiêu cực
    """
    if not config.ANTHROPIC_API_KEY:
        return _rule_based_sentiment(news_items)

    if not news_items:
        return {"score": 0.0, "summary": "Không có tin tức liên quan trong khoảng thời gian theo dõi."}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        news_text = "\n".join(
            f"- [{n['source']}] {n['title']}: {n['summary']}" for n in news_items[:10]
        )
        prompt = f"""Bạn là chuyên gia phân tích chứng khoán Việt Nam.
Dưới đây là các tin tức gần đây liên quan tới mã cổ phiếu {symbol}:

{news_text}

Hãy đánh giá mức độ ảnh hưởng của các tin này tới giá cổ phiếu {symbol} trong ngắn hạn.
Trả lời CHỈ bằng JSON với format chính xác sau, không thêm chữ nào khác:
{{"score": <số thực từ -1.0 (rất tiêu cực) đến 1.0 (rất tích cực)>, "summary": "<tóm tắt nhận định trong 1-2 câu tiếng Việt>"}}"""

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        raw_text = raw_text.strip()
        raw_text = re.sub(r"^```json|```$", "", raw_text).strip()
        parsed = json.loads(raw_text)
        score = max(-1.0, min(1.0, float(parsed.get("score", 0))))
        return {"score": round(score, 2), "summary": parsed.get("summary", "")}

    except Exception as e:
        logger.warning("Lỗi gọi Anthropic API, fallback rule-based: %s", e)
        return _rule_based_sentiment(news_items)


def predict_probability(technical: dict, news_sentiment: dict) -> dict:
    """
    Tổng hợp các tín hiệu thành xác suất tăng giá (0-100%).

    technical: kết quả từ indicators.analyze_symbol()
    news_sentiment: kết quả từ analyze_news_sentiment()
    """
    w = config.WEIGHTS

    # --- điểm RSI: quá bán -> nghiêng tăng (hồi phục), quá mua -> nghiêng giảm
    rsi = technical["rsi"]
    if rsi <= config.RSI_OVERSOLD:
        rsi_score = 0.8
    elif rsi >= config.RSI_OVERBOUGHT:
        rsi_score = -0.8
    else:
        # vùng trung tính: nội suy tuyến tính quanh điểm giữa (50 -> 0 điểm)
        rsi_score = (50 - rsi) / 20.0
        rsi_score = max(-0.5, min(0.5, rsi_score)) * -1  # >50 nghiêng tăng nhẹ theo đà

    # --- điểm xu hướng MA20
    ma_score = {"tăng": 0.8, "giảm": -0.8, "đi ngang": 0.0}.get(technical["ma_trend"], 0.0)

    # --- điểm breakout
    breakout = technical["breakout"]
    if breakout.get("is_breakout"):
        breakout_score = 1.0
    else:
        breakout_score = 0.0

    # --- điểm tin tức
    news_score = news_sentiment.get("score", 0.0)

    total_score = (
        w["rsi"] * rsi_score
        + w["ma_trend"] * ma_score
        + w["breakout"] * breakout_score
        + w["news_sentiment"] * news_score
    )

    # Chuẩn hoá từ [-1, 1] về [0, 100]%, neo quanh 50% (trung tính)
    probability = round(50 + total_score * 50, 1)
    probability = max(1.0, min(99.0, probability))

    if probability >= 65:
        label = "Xác suất tăng giá CAO"
    elif probability >= 50:
        label = "Xác suất tăng giá vừa phải / trung tính nghiêng tăng"
    elif probability >= 35:
        label = "Trung tính nghiêng giảm"
    else:
        label = "Xác suất giảm giá CAO"

    return {
        "probability_up_pct": probability,
        "label": label,
        "components": {
            "rsi_score": round(rsi_score, 2),
            "ma_score": round(ma_score, 2),
            "breakout_score": round(breakout_score, 2),
            "news_score": round(news_score, 2),
        },
    }
