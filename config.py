"""
config.py
---------
Cau hinh trung tam cho bot. Tat ca thong tin nhay cam (token, key) duoc
doc tu bien moi truong (GitHub Secrets / file .env) de khong bi lo.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ====== TELEGRAM ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ====== DANH SACH MA THEO DOI (HOSE/HNX) ======
WATCHLIST = [
    "VNM", "VNM", "FPT", "HPG", "VIC",
    "POW", "VHM", "MBB", "TCB",
]

# ====== THAM SO KY THUAT ======
RSI_PERIOD      = 14
RSI_OVERBOUGHT  = 70
RSI_OVERSOLD    = 30

MA_PERIOD = 20

BREAKOUT_LOOKBACK           = 20
BREAKOUT_VOLUME_MULTIPLIER  = 1.5

HISTORY_DAYS = 120

# ====== NGUON TIN TUC (RSS) ======
NEWS_RSS_FEEDS = {
    "CafeF":            "https://cafef.vn/thi-truong-chung-khoan.rss",
    "VietstockFinance": "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "NDH":              "https://ndh.vn/chung-khoan.rss",
}
NEWS_MAX_ITEMS_PER_FEED = 15
NEWS_LOOKBACK_HOURS     = 18

# ====== LICH BAO CAO TU DONG ======
TIMEZONE     = "Asia/Ho_Chi_Minh"
REPORT_TIMES = [
    {"hour": 8,  "minute": 0},
    {"hour": 13, "minute": 0},
]

# ====== CANH BAO BREAKOUT REAL-TIME ======
TRADING_SESSIONS = [
    {"start": "09:15", "end": "11:30"},
    {"start": "13:00", "end": "14:45"},
]
REALTIME_SCAN_INTERVAL_MINUTES = 15
REALTIME_SCAN_WEEKDAYS_ONLY    = True
STATE_FILE = "state/breakout_state.json"

# ====== DE XUAT DIEM VAO / DUNG LO / CHOT LOI ======
STOP_LOSS_ATR_MULTIPLIER    = 1.5
RISK_REWARD_TARGET          = 2.0
PULLBACK_MAX_DISTANCE_PCT   = 3.0

# ====== TRONG SO XAC SUAT TANG GIA ======
WEIGHTS = {
    "rsi":            0.25,
    "ma_trend":       0.25,
    "breakout":       0.30,
    "news_sentiment": 0.20,
}

# ====== API KEYS (doc tu bien moi truong / GitHub Secrets) ======
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")

# Model su dung
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
OPENAI_MODEL    = "gpt-4o-mini"
GEMINI_MODEL    = "gemini-2.0-flash"
