"""
telegram_notifier.py
---------------------
Gửi tin nhắn tới Telegram qua Bot API (dùng requests trực tiếp, không
cần thư viện python-telegram-bot, đơn giản và đủ dùng cho việc gửi
thông báo 1 chiều như thế này).
"""
import logging
import requests

import config

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Gửi 1 tin nhắn. Tự động chia nhỏ nếu vượt giới hạn 4096 ký tự của Telegram."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong .env")
        return False

    url = API_URL.format(token=config.TELEGRAM_BOT_TOKEN)
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [text]

    ok = True
    for chunk in chunks:
        try:
            resp = requests.post(url, data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }, timeout=15)
            if not resp.ok:
                logger.error("Telegram API lỗi: %s - %s", resp.status_code, resp.text)
                ok = False
        except Exception as e:
            logger.error("Lỗi gửi Telegram: %s", e)
            ok = False
    return ok


def escape_markdown(text: str) -> str:
    """Escape các ký tự đặc biệt của Markdown Telegram để tránh lỗi format."""
    special = ["_", "*", "`", "["]
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    send_message("🔔 Test bot chứng khoán VN - kết nối Telegram thành công!")
