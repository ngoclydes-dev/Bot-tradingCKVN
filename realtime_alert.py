"""
realtime_alert.py
-------------------
Quét nhanh toàn bộ watchlist để phát hiện breakout MỚI trong giờ giao
dịch (khác với báo cáo đầy đủ 8h/15h vốn gửi toàn bộ phân tích).

Đặc điểm:
- Chỉ gửi Telegram khi: (1) đang trong phiên giao dịch (market_hours),
  (2) phát hiện breakout, và (3) mã đó CHƯA được cảnh báo trong hôm nay
  (tránh spam mỗi 15 phút cho cùng 1 tín hiệu - xem state_store.py).
- Không gọi AI/tin tức ở đây để giữ tốc độ quét nhanh, nhẹ. Phân tích
  đầy đủ (tin tức + AI + xác suất) vẫn có trong báo cáo 8h/15h.
"""
import logging
import config
import data_fetcher
import indicators
import entry_strategy
import market_hours
import state_store
import telegram_notifier

# ── Đảm bảo file state luôn tồn tại dù có breakout hay không ──
import json, os
if not os.path.exists(config.STATE_FILE):
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("realtime_alert")


def format_breakout_alert(symbol: str, technical: dict) -> str:
    b = technical["breakout"]
    entry = entry_strategy.suggest_entry(technical)
    return (
        f"🚨 *BREAKOUT REAL-TIME: {symbol}*\n"
        f"Giá hiện tại: {technical['last_close']:,.0f} đ ({technical['change_pct']:+.2f}%)\n"
        f"Vượt kháng cự: {b['resistance_level']:,.0f} đ | Volume x{b['volume_ratio']}\n"
        f"RSI({config.RSI_PERIOD}): {technical['rsi']} ({technical['rsi_state']}) | "
        f"MA20: {technical['ma20']:,.0f} ({technical['ma_trend']})\n\n"
        f"{entry_strategy.format_entry_block(entry)}\n\n"
        f"_Đây là cảnh báo kỹ thuật nhanh, xem báo cáo 8h/15h để có phân tích AI + tin tức đầy đủ._"
    )


def run_realtime_scan(force: bool = False) -> list[str]:
    """
    Quét 1 lần toàn bộ watchlist. Trả về list các mã vừa được cảnh báo.
    force=True: bỏ qua kiểm tra giờ giao dịch (dùng để test thủ công).
    """
    if not force and not market_hours.is_trading_session():
        logger.info("Ngoài giờ giao dịch — bỏ qua lần quét này.")
        return []

    alerted = []
    for symbol in config.WATCHLIST:
        try:
            df = data_fetcher.get_stock_history(symbol, days=config.HISTORY_DAYS)
        except Exception as e:
            logger.warning("Bỏ qua %s do lỗi dữ liệu: %s", symbol, e)
            continue

        technical = indicators.analyze_symbol(df)
        if not technical["breakout"]["is_breakout"]:
            continue

        if state_store.was_alerted_today(symbol):
            logger.info("%s đã breakout nhưng đã cảnh báo hôm nay rồi, bỏ qua.", symbol)
            continue

        message = format_breakout_alert(symbol, technical)
        if telegram_notifier.send_message(message):
            logger.info("Đã gửi cảnh báo breakout real-time cho %s", symbol)
            state_store.mark_alerted_today(symbol)
            alerted.append(symbol)
        else:
            logger.error("Gửi cảnh báo thất bại cho %s", symbol)

    if not alerted:
        logger.info("Quét xong — không có breakout mới.")
    return alerted


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    run_realtime_scan(force=force)
