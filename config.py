"""
config.py
---------
Cấu hình trung tâm cho bot. Tất cả thông tin nhạy cảm (token, key) được
đọc từ file .env (xem .env.example) để không bị lộ khi đẩy code lên git.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ====== TELEGRAM ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ====== ANTHROPIC (AI phân tích tin tức + nhận định) ======
# Để trống nếu chưa có key -> bot sẽ tự dùng phân tích rule-based, vẫn hoạt động.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ====== DANH SÁCH MÃ THEO DÕI (HOSE/HNX) ======
# Thêm/sửa mã tùy ý. Có thể tách riêng theo sàn nếu cần.
WATCHLIST = [
    "VNM", "VCB", "FPT", "VIC", "SSI", "VHM", "POW", "TCB",
]

# ====== THAM SỐ KỸ THUẬT ======
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

MA_PERIOD = 20

# Breakout: giá đóng cửa vượt mức cao nhất N phiên gần nhất kèm volume xác nhận
BREAKOUT_LOOKBACK = 20          # số phiên để xác định vùng kháng cự
BREAKOUT_VOLUME_MULTIPLIER = 1.5  # volume phải >= 1.5x volume TB 20 phiên

# Số ngày dữ liệu lịch sử cần tải để tính đủ chỉ báo
HISTORY_DAYS = 120

# ====== NGUỒN TIN TỨC (RSS) ======
NEWS_RSS_FEEDS = {
    "CafeF": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "VietstockFinance": "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "NDH": "https://ndh.vn/chung-khoan.rss",
}
NEWS_MAX_ITEMS_PER_FEED = 15
NEWS_LOOKBACK_HOURS = 18  # chỉ lấy tin trong khoảng X giờ gần nhất

# ====== LỊCH BÁO CÁO TỰ ĐỘNG ======
TIMEZONE = "Asia/Ho_Chi_Minh"
REPORT_TIMES = [
    {"hour": 8, "minute": 0},   # báo cáo sáng - trước/đầu phiên
    {"hour": 15, "minute": 0},  # báo cáo chiều - cuối phiên
]

# ====== CẢNH BÁO BREAKOUT REAL-TIME TRONG GIỜ GIAO DỊCH ======
# Phiên sáng HOSE/HNX: 9h00-11h30 | Phiên chiều: 13h00-15h00
# Để tránh tín hiệu nhiễu ngay lúc ATO/ATC, mặc định quét từ 9h15-11h30 và 13h00-14h45.
TRADING_SESSIONS = [
    {"start": "09:15", "end": "11:30"},
    {"start": "13:00", "end": "14:45"},
]
REALTIME_SCAN_INTERVAL_MINUTES = 15  # tần suất quét breakout trong giờ giao dịch
REALTIME_SCAN_WEEKDAYS_ONLY = True

# File lưu trạng thái đã cảnh báo (để tránh gửi trùng nhiều lần/ngày cho cùng 1 mã)
STATE_FILE = "state/breakout_state.json"

# ====== ĐỀ XUẤT ĐIỂM VÀO / DỪNG LỖ / CHỐT LỜI ======
STOP_LOSS_ATR_MULTIPLIER = 1.5   # dừng lỗ = mức tham chiếu - 1.5 x ATR(14)
RISK_REWARD_TARGET = 2.0          # tỷ lệ Reward:Risk mục tiêu khi không có kháng cự rõ để làm target
PULLBACK_MAX_DISTANCE_PCT = 3.0   # giá lệch khỏi MA20 tối đa bao nhiêu % để còn coi là "đang pullback"

# ====== TRỌNG SỐ CHO MÔ HÌNH XÁC SUẤT TĂNG GIÁ ======
# Tổng các trọng số kỹ thuật + tin tức = 1.0
WEIGHTS = {
    "rsi": 0.25,
    "ma_trend": 0.25,
    "breakout": 0.30,
    "news_sentiment": 0.20,
}
