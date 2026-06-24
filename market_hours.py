"""
market_hours.py
-----------------
Kiểm tra thời điểm hiện tại có nằm trong phiên giao dịch HOSE/HNX không,
dựa trên config.TRADING_SESSIONS. Dùng để job quét real-time tự bỏ qua
giờ nghỉ trưa, ngoài giờ, và cuối tuần mà không cần cron phức tạp.
"""
from datetime import datetime, time as dtime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python <3.9 fallback (không cần thiết với Python 3.12 hiện tại)
    ZoneInfo = None

import config


def _now_vn() -> datetime:
    if ZoneInfo:
        return datetime.now(ZoneInfo(config.TIMEZONE))
    return datetime.now()


def is_trading_session(now: datetime | None = None) -> bool:
    """True nếu thời điểm `now` (mặc định = hiện tại, giờ VN) nằm trong 1 phiên giao dịch
    và là ngày trong tuần (nếu REALTIME_SCAN_WEEKDAYS_ONLY=True)."""
    now = now or _now_vn()

    if config.REALTIME_SCAN_WEEKDAYS_ONLY and now.weekday() >= 5:  # 5=Sat, 6=Sun
        return False

    current_t = now.time()
    for session in config.TRADING_SESSIONS:
        start_h, start_m = map(int, session["start"].split(":"))
        end_h, end_m = map(int, session["end"].split(":"))
        if dtime(start_h, start_m) <= current_t <= dtime(end_h, end_m):
            return True
    return False


if __name__ == "__main__":
    now = _now_vn()
    print(f"Thời gian hiện tại (VN): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Đang trong phiên giao dịch: {is_trading_session(now)}")
