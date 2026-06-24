"""
news_fetcher.py
----------------
Lấy tin tức chứng khoán Việt Nam từ các nguồn RSS công khai (CafeF,
Vietstock, NDH...). Dùng RSS thay vì scrape HTML trực tiếp để ổn định
hơn và tránh các vấn đề chặn bot / thay đổi cấu trúc trang.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser

import config

logger = logging.getLogger(__name__)


def _parse_entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_all_news(lookback_hours: int = config.NEWS_LOOKBACK_HOURS) -> list[dict]:
    """
    Trả về list các tin: {source, title, summary, link, published}
    đã lọc theo khoảng thời gian gần nhất, sắp xếp mới nhất trước.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    all_items = []

    for source, url in config.NEWS_RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning("RSS lỗi/không đọc được: %s (%s)", source, url)
                continue

            for entry in feed.entries[:config.NEWS_MAX_ITEMS_PER_FEED]:
                published = _parse_entry_time(entry)
                if published and published < cutoff:
                    continue
                summary = re.sub("<[^<]+?>", "", getattr(entry, "summary", "")).strip()
                all_items.append({
                    "source": source,
                    "title": entry.title.strip(),
                    "summary": summary[:300],
                    "link": entry.link,
                    "published": published.isoformat() if published else None,
                })
        except Exception as e:
            logger.warning("Không lấy được RSS từ %s: %s", source, e)

    all_items.sort(key=lambda x: x["published"] or "", reverse=True)
    return all_items


def filter_news_by_symbol(news_items: list[dict], symbol: str, company_keywords: list[str] | None = None) -> list[dict]:
    """
    Lọc tin liên quan tới 1 mã cổ phiếu cụ thể, dựa trên mã (VD: 'VNM')
    hoặc các từ khoá tên công ty nếu được cung cấp (giúp tăng độ chính xác,
    vì nhiều bài báo không nêu thẳng mã mà nêu tên công ty).
    """
    keywords = [symbol] + (company_keywords or [])
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)

    matched = []
    for item in news_items:
        text = f"{item['title']} {item['summary']}"
        if pattern.search(text):
            matched.append(item)
    return matched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    items = fetch_all_news()
    print(f"Tổng số tin lấy được: {len(items)}")
    for it in items[:5]:
        print(f"- [{it['source']}] {it['title']}")
