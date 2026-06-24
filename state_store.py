"""
state_store.py
----------------
Lưu trạng thái "đã cảnh báo breakout cho mã X vào ngày Y" ra file JSON
đơn giản, để job quét real-time (chạy mỗi 15 phút) không gửi trùng lặp
nhiều lần cho cùng 1 tín hiệu trong cùng 1 ngày.

Không dùng database để giữ project gọn nhẹ, dễ chạy trên VPS nhỏ.
Nếu cần chạy nhiều instance song song hoặc cần độ tin cậy cao hơn, có
thể thay bằng SQLite/Redis mà không ảnh hưởng tới phần logic còn lại.
"""
import json
import os
from datetime import date

import config


def _ensure_dir():
    folder = os.path.dirname(config.STATE_FILE)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(config.STATE_FILE):
        return {}
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    _ensure_dir()
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def was_alerted_today(symbol: str) -> bool:
    """True nếu mã này đã được gửi cảnh báo breakout trong hôm nay."""
    data = _load()
    today = date.today().isoformat()
    return data.get(symbol) == today


def mark_alerted_today(symbol: str):
    """Ghi nhận đã gửi cảnh báo cho mã này hôm nay."""
    data = _load()
    data[symbol] = date.today().isoformat()
    _save(data)


def reset_state():
    """Xoá toàn bộ trạng thái (dùng khi test hoặc muốn cảnh báo lại từ đầu)."""
    _save({})
