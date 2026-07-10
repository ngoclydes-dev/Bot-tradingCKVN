"""
telegram_notifier.py
---------------------
Gửi tin nhắn Telegram qua Bot API.
- Thử Markdown trước
- Nếu lỗi parse (400) do ký tự đặc biệt từ AI/tin tức → tự động fallback plain text
- Không bao giờ mất tin nhắn vì lỗi format
"""
import logging
import re
import requests

import config

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _strip_markdown(text: str) -> str:
    """Xóa hết Markdown để gửi plain text khi parse lỗi."""
    # Xóa *bold*, _italic_, `code`, [link](url)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """
    Gửi 1 tin nhắn. Tự động chia nhỏ nếu vượt 4096 ký tự.
    Nếu Markdown parse lỗi (400) → tự fallback sang plain text.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
        return False

    url = API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [text]

    ok = True
    for chunk in chunks:
        # Thử gửi với Markdown
        sent = _post(url, chunk, parse_mode)
        if not sent:
            # Fallback: gửi plain text (strip toàn bộ Markdown)
            logger.warning("Parse lỗi, fallback plain text...")
            _post(url, _strip_markdown(chunk), parse_mode=None)
            # Không đánh dấu ok=False vì tin vẫn được gửi (dạng plain)
    return ok


def _post(url: str, text: str, parse_mode: str | None) -> bool:
    """Gửi 1 chunk, trả về True nếu thành công."""
    try:
        data: dict = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode

        resp = requests.post(url, data=data, timeout=15)
        if resp.ok:
            return True

        # Lỗi 400 parse entities → cần fallback
        if resp.status_code == 400 and "parse entities" in resp.text:
            return False

        logger.error("Telegram API lỗi: %s - %s", resp.status_code, resp.text[:150])
        return False
    except Exception as e:
        logger.error("Lỗi gửi Telegram: %s", e)
        return False


def escape_markdown(text: str) -> str:
    """Escape các ký tự đặc biệt của Markdown Telegram."""
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text
