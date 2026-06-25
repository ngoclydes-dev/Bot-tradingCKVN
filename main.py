"""
main.py
-------
Điều phối toàn bộ luồng:

    Python -> Lấy dữ liệu HOSE/HNX -> RSI -> MA20 -> Breakout
           -> Tin tức -> Phân tích AI -> Xác suất tăng giá -> Telegram

Có 2 cách chạy:
  1. python main.py            -> chạy ngay 1 lần, gửi báo cáo full watchlist
  2. python main.py --scan SYM -> chỉ phân tích nhanh 1 mã, in ra terminal
  3. python scheduler.py       -> chạy nền, tự gửi báo cáo lúc 8h00 & 15h00
"""
import argparse
import logging
import sys

import config
import data_fetcher
import indicators
import news_fetcher
import ai_analyzer
import entry_strategy
import telegram_notifier
import state_store 
import json, os
if not os.path.exists(config.STATE_FILE):
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def analyze_one_symbol(symbol: str, all_news: list[dict]) -> dict | None:
    """Chạy toàn bộ pipeline cho 1 mã, trả về dict kết quả tổng hợp hoặc None nếu lỗi."""
    try:
        df = data_fetcher.get_stock_history(symbol, days=config.HISTORY_DAYS)
    except Exception as e:
        logger.warning("Bỏ qua %s do lỗi dữ liệu: %s", symbol, e)
        return None

    technical = indicators.analyze_symbol(df)
    symbol_news = news_fetcher.filter_news_by_symbol(all_news, symbol)
    sentiment = ai_analyzer.analyze_news_sentiment(symbol, symbol_news)
    prediction = ai_analyzer.predict_probability(technical, sentiment)
    entry = entry_strategy.suggest_entry(technical)

    return {
        "symbol": symbol,
        "technical": technical,
        "news": symbol_news,
        "sentiment": sentiment,
        "prediction": prediction,
        "entry": entry,
    }


def format_symbol_block(result: dict) -> str:
    """Format kết quả 1 mã thành đoạn text Markdown cho Telegram."""
    t = result["technical"]
    p = result["prediction"]
    b = t["breakout"]

    change_sign = "📈" if t["change_pct"] >= 0 else "📉"
    breakout_flag = "🚀 *BREAKOUT*" if b["is_breakout"] else "—"

    lines = [
        f"*{result['symbol']}* — {t['last_close']:,.0f} đ  ({change_sign} {t['change_pct']:+.2f}%)",
        f"RSI({config.RSI_PERIOD}): {t['rsi']} ({t['rsi_state']}) | MA20: {t['ma20']:,.0f} | Xu hướng MA: {t['ma_trend']}",
        f"Breakout: {breakout_flag}"
        + (f" — vượt kháng cự {b['resistance_level']:,.0f}, vol x{b['volume_ratio']}" if b["is_breakout"] else ""),
        f"Tin tức liên quan: {len(result['news'])} bài | Sentiment AI: {result['sentiment']['score']:+.2f}",
        f"➡️ *Xác suất tăng giá: {p['probability_up_pct']}%* — {p['label']}",
        entry_strategy.format_entry_block(result["entry"]),
    ]
    return "\n".join(lines)


def build_full_report(period_label: str) -> str:
    """Xây dựng báo cáo đầy đủ cho toàn bộ watchlist."""
    logger.info("Đang lấy tin tức...")
    all_news = news_fetcher.fetch_all_news()

    blocks = []
    breakout_symbols = []
    high_prob_symbols = []

    for symbol in config.WATCHLIST:
        logger.info("Đang phân tích %s ...", symbol)
        result = analyze_one_symbol(symbol, all_news)
        if result is None:
            continue
        blocks.append(format_symbol_block(result))
        if result["technical"]["breakout"]["is_breakout"]:
            breakout_symbols.append(symbol)
        if result["prediction"]["probability_up_pct"] >= 65:
            high_prob_symbols.append(symbol)

    header = f"📊 *BÁO CÁO CHỨNG KHOÁN VN — {period_label}*\n"
    summary = ""
    if breakout_symbols:
        summary += f"🚀 Mã breakout: {', '.join(breakout_symbols)}\n"
    if high_prob_symbols:
        summary += f"🔥 Xác suất tăng cao (≥65%): {', '.join(high_prob_symbols)}\n"
    if not breakout_symbols and not high_prob_symbols:
        summary += "Chưa có tín hiệu nổi bật trong phiên này.\n"

    body = "\n\n".join(blocks) if blocks else "_Không lấy được dữ liệu cho bất kỳ mã nào._"

    return f"{header}{summary}\n{body}"


def run_full_report(period_label: str = "Báo cáo định kỳ"):
    report = build_full_report(period_label)
    sent = telegram_notifier.send_message(report)
    if sent:
        logger.info("Đã gửi báo cáo Telegram thành công.")
    else:
        logger.error("Gửi báo cáo Telegram thất bại — kiểm tra lại .env / log phía trên.")
    return report


def run_single_scan(symbol: str):
    all_news = news_fetcher.fetch_all_news()
    result = analyze_one_symbol(symbol.upper(), all_news)
    if result is None:
        print(f"Không lấy được dữ liệu cho mã {symbol}")
        return
    print(format_symbol_block(result))
    if result["sentiment"].get("summary"):
        print(f"\nNhận định AI: {result['sentiment']['summary']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot phân tích & cảnh báo chứng khoán Việt Nam")
    parser.add_argument("--scan", help="Chỉ phân tích nhanh 1 mã (in ra terminal, không gửi Telegram)")
    parser.add_argument("--no-telegram", action="store_true", help="Chỉ in báo cáo ra terminal, không gửi Telegram")
    parser.add_argument("--label", default=None, help="Nhãn hiển thị trên báo cáo (VD: 'Báo cáo SÁNG (08:00)'), dùng khi gọi từ GitHub Actions/cron")
    args = parser.parse_args()

    if args.scan:
        run_single_scan(args.scan)
    elif args.no_telegram:
        print(build_full_report(args.label or "Chạy thủ công"))
    else:
        run_full_report(args.label or "Chạy thủ công")
