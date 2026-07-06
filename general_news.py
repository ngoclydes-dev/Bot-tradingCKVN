"""
general_news.py
---------------
Lấy tin tức tổng hợp từ các báo lớn Việt Nam (VnExpress, Tuổi Trẻ,
Thanh Niên, CafeF, VnEconomy...) — không chỉ tin chứng khoán mà cả
kinh tế vĩ mô, chính sách, thế giới có thể ảnh hưởng thị trường.

Gemini đọc các tin này và tóm tắt thành 1 khối nhận định:
- Điểm tin nổi bật trong ngày
- Tác động tiềm năng lên thị trường chứng khoán
- Yếu tố vĩ mô cần theo dõi
"""
import logging
import re
import json
from datetime import datetime, timedelta, timezone

import feedparser
import requests

import config

logger = logging.getLogger(__name__)


def fetch_general_news(lookback_hours: int = config.GENERAL_NEWS_LOOKBACK_HOURS) -> list[dict]:
    """Lấy tin tức tổng hợp từ tất cả nguồn trong GENERAL_NEWS_RSS_FEEDS."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    all_items = []

    for source, url in config.GENERAL_NEWS_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning("RSS lỗi: %s (%s)", source, url)
                continue

            count = 0
            for entry in feed.entries:
                if count >= config.GENERAL_NEWS_MAX_ITEMS:
                    break

                # Kiểm tra thời gian
                published = None
                for key in ("published_parsed", "updated_parsed"):
                    t = getattr(entry, key, None)
                    if t:
                        published = datetime(*t[:6], tzinfo=timezone.utc)
                        break

                if published and published < cutoff:
                    continue

                summary = re.sub("<[^<]+?>", "", getattr(entry, "summary", "")).strip()
                all_items.append({
                    "source": source,
                    "title": entry.title.strip(),
                    "summary": summary[:200],
                    "link": getattr(entry, "link", ""),
                    "published": published.isoformat() if published else None,
                })
                count += 1

        except Exception as e:
            logger.warning("Không lấy được RSS %s: %s", source, e)

    all_items.sort(key=lambda x: x["published"] or "", reverse=True)
    logger.info("Lấy được %d tin tổng hợp từ %d nguồn",
                len(all_items), len(config.GENERAL_NEWS_RSS_FEEDS))
    return all_items


def _analyze_with_gemini(news_items: list[dict]) -> dict | None:
    """Dùng Gemini phân tích tin tức tổng hợp, trả về JSON nhận định."""
    if not config.GEMINI_API_KEY or not news_items:
        return None

    # Rút gọn danh sách tin để tiết kiệm token
    top_news = news_items[:20]
    news_text = "\n".join(
        f"- [{n['source']}] {n['title']}"
        for n in top_news
    )

    prompt = f"""Bạn là chuyên gia phân tích kinh tế vĩ mô Việt Nam.
Dưới đây là các tin tức tổng hợp trong {config.GENERAL_NEWS_LOOKBACK_HOURS} giờ qua:

{news_text}

Phân tích tác động của các tin này lên thị trường chứng khoán Việt Nam.
Trả lời CHỈ bằng JSON:
{{"market_impact":"<tich_cuc|tieu_cuc|trung_tinh>","highlights":["<tin 1>","<tin 2>","<tin 3>"],"macro_factors":"<yeu to vi mo noi bat 1 cau>","stock_impact":"<nhan dinh tac dong len TTCK 2 cau>"}}"""

    models = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    for model in models:
        try:
            url = f"{base_url}/{model}:generateContent?key={config.GEMINI_API_KEY}"
            resp = requests.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400},
            }, timeout=20)

            if resp.status_code == 200:
                raw = (resp.json().get("candidates", [{}])[0]
                                  .get("content", {})
                                  .get("parts", [{}])[0]
                                  .get("text", ""))
                text = re.sub(r"```(?:json)?|```", "", raw).strip()
                try:
                    result = json.loads(text)
                    if result:
                        return result
                except json.JSONDecodeError:
                    match = re.search(r"\{.*\}", text, re.DOTALL)
                    if match:
                        try:
                            return json.loads(match.group())
                        except Exception:
                            pass
            elif resp.status_code == 429:
                logger.warning("Gemini general_news 429 rate limit")
                continue

        except Exception as e:
            logger.warning("Gemini general_news lỗi: %s", e)
            continue

    return None


def _rule_based_summary(news_items: list[dict]) -> str:
    """Fallback không cần AI — chỉ liệt kê tin nổi bật."""
    if not news_items:
        return ""
    lines = [
        "📰 *TIN TỨC VĨ MÔ & KINH TẾ*",
        f"_(Tổng hợp từ {len(set(n['source'] for n in news_items))} nguồn)_",
        "",
    ]
    # Lấy 5 tin đầu từ các nguồn khác nhau
    seen_sources = set()
    shown = 0
    for item in news_items:
        if shown >= 5:
            break
        bullet = f"• [{item['source']}] {item['title']}"
        lines.append(bullet)
        shown += 1
    return "\n".join(lines)


def get_general_news_block() -> str:
    """
    Hàm chính — lấy tin, phân tích AI, trả về chuỗi Markdown cho Telegram.
    Luôn trả về string (rỗng nếu không có tin, không bao giờ crash).
    """
    try:
        news_items = fetch_general_news()
        if not news_items:
            return ""

        ai_result = _analyze_with_gemini(news_items)

        if not ai_result:
            return _rule_based_summary(news_items)

        impact_icon = {
            "tich_cuc": "🟢", "tieu_cuc": "🔴", "trung_tinh": "🟡"
        }.get(ai_result.get("market_impact", ""), "⚪")

        lines = [
            "─" * 30,
            f"📰 *TIN TỨC VĨ MÔ & KINH TẾ — Gemini tóm tắt*",
            f"{impact_icon} Tác động thị trường: "
            f"*{ai_result.get('market_impact','?').replace('_',' ').upper()}*",
            "",
        ]

        # Điểm tin nổi bật
        highlights = ai_result.get("highlights", [])
        if highlights:
            lines.append("📌 *Tin nổi bật:*")
            for h in highlights[:3]:
                lines.append(f"• {h}")
            lines.append("")

        if ai_result.get("macro_factors"):
            lines.append(f"📊 *Yếu tố vĩ mô:* {ai_result['macro_factors']}")

        if ai_result.get("stock_impact"):
            lines.append(f"💹 *Nhận định TTCK:* _{ai_result['stock_impact']}_")

        return "\n".join(lines)

    except Exception as e:
        logger.warning("get_general_news_block lỗi: %s", e)
        return ""
