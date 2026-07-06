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
import random
import sys

import config
import data_fetcher
import indicators
import news_fetcher
import ai_analyzer
import entry_strategy
import deep_analysis
import market_summary_ai
import general_news
import telegram_notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

# ====== CÂU QUOTE CHO BÁO CÁO ======
QUOTES = [
    # Quản trị rủi ro
    ("Quy tắc số 1: đừng bao giờ thua lỗ. Quy tắc số 2: đừng quên quy tắc số 1.", "Warren Buffett"),
    ("Rủi ro đến từ việc không biết mình đang làm gì.", "Warren Buffett"),
    ("Thị trường có thể phi lý lâu hơn bạn có thể duy trì khả năng thanh khoản.", "John Maynard Keynes"),
    ("Không phải về việc đúng hay sai — mà về việc bạn kiếm được bao nhiêu khi đúng và mất bao nhiêu khi sai.", "George Soros"),
    ("Điều quan trọng nhất khi đầu tư là bảo toàn vốn, sau đó mới nghĩ đến lợi nhuận.", "Jesse Livermore"),

    # Kỷ luật & tâm lý
    ("Thị trường chứng khoán là công cụ chuyển tiền từ người thiếu kiên nhẫn sang người kiên nhẫn.", "Warren Buffett"),
    ("Kẻ thù lớn nhất của nhà đầu tư chính là bản thân họ.", "Benjamin Graham"),
    ("Đừng để cảm xúc điều khiển quyết định đầu tư của bạn.", "Peter Lynch"),
    ("Mua khi người khác sợ hãi, bán khi người khác tham lam.", "Warren Buffett"),
    ("Kỷ luật là cầu nối giữa mục tiêu và thành tựu.", "Jim Rohn"),
    ("Thành công trong đầu tư không đến từ IQ cao mà đến từ kỷ luật cảm xúc.", "Benjamin Graham"),

    # Chiến lược & phân tích
    ("Xu hướng là bạn của bạn — cho đến khi nó kết thúc.", "Ed Seykota"),
    ("Hãy cắt lỗ ngắn và để lợi nhuận chạy dài.", "Jesse Livermore"),
    ("Đừng bắt đáy, hãy mua khi xu hướng đã xác nhận.", "Vô danh"),
    ("Phân tích kỹ thuật không phải để đoán tương lai, mà để quản lý xác suất.", "Vô danh"),
    ("Volume là dấu chân của dòng tiền thông minh.", "Vô danh"),
    ("Giá cả là thứ bạn trả. Giá trị là thứ bạn nhận được.", "Warren Buffett"),
    ("Hãy sợ khi người khác tham lam và tham lam khi người khác sợ.", "Warren Buffett"),

    # Học hỏi & kiên nhẫn
    ("Thị trường là người thầy tốt nhất — nhưng học phí rất đắt.", "Vô danh"),
    ("Nhà đầu tư giỏi nhất thế giới đều có một điểm chung: họ kiên nhẫn hơn người khác.", "Vô danh"),
    ("Đầu tư là quá trình tự học không ngừng. Ngày bạn ngừng học là ngày bạn bắt đầu thua lỗ.", "Vô danh"),
    ("Mỗi ngày thị trường đều dạy bạn điều gì đó — hãy luôn sẵn sàng học.", "Vô danh"),
    ("Không ai có thể đánh bại thị trường mãi mãi — hãy tôn trọng nó.", "Vô danh"),
]


def get_daily_quote() -> str:
    """
    Lấy câu quote theo ngày (dùng ngày làm seed) để cùng 1 ngày luôn
    ra cùng 1 câu, tránh báo cáo sáng/chiều ra 2 câu khác nhau.
    """
    from datetime import date
    seed = int(date.today().strftime("%Y%m%d"))
    rng = random.Random(seed)
    quote, author = rng.choice(QUOTES)
    return f'💬 _"{quote}"_\n— {author}'


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
    all_results = []   # lưu để truyền cho market_summary_ai
    breakout_symbols = []
    high_prob_symbols = []

    for symbol in config.WATCHLIST:
        logger.info("Đang phân tích %s ...", symbol)
        result = analyze_one_symbol(symbol, all_news)
        if result is None:
            continue
        blocks.append(format_symbol_block(result))
        all_results.append(result)
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

    # Tổng kết thị trường bằng đa AI (gọi 1 lần cho cả watchlist)
    logger.info("Đang tổng hợp nhận định thị trường từ đa AI...")
    market_block = market_summary_ai.get_market_summary(all_results, period_label)

    # Tin tức vĩ mô & kinh tế tổng hợp
    logger.info("Đang lấy tin tức tổng hợp vĩ mô...")
    general_block = general_news.get_general_news_block()

    quote = get_daily_quote()
    return f"{header}{summary}\n{body}\n\n{market_block}\n\n{general_block}\n\n{quote}"


def run_full_report(period_label: str = "Báo cáo định kỳ"):
    report = build_full_report(period_label)
    sent = telegram_notifier.send_message(report)
    if sent:
        logger.info("Đã gửi báo cáo Telegram thành công.")
    else:
        logger.error("Gửi báo cáo Telegram thất bại — kiểm tra lại .env / log phía trên.")
    return report


def run_single_scan(symbol: str, send_telegram: bool = False):
    """Phân tích chuyên sâu 1 mã — chi tiết hơn nhiều so với báo cáo hằng ngày."""
    logger.info("Bắt đầu phân tích chuyên sâu mã %s ...", symbol)
    symbol = symbol.upper()

    try:
        df = data_fetcher.get_stock_history(symbol, days=config.HISTORY_DAYS)
    except Exception as e:
        msg = f"❌ Không lấy được dữ liệu cho mã *{symbol}* — mã có thể không hợp lệ hoặc nguồn dữ liệu tạm lỗi.\n_{e}_"
        if send_telegram:
            telegram_notifier.send_message(msg)
        else:
            print(msg)
        return

    # Phân tích cơ bản (dùng chung với báo cáo hằng ngày)
    technical   = indicators.analyze_symbol(df)
    symbol_news = news_fetcher.filter_news_by_symbol(
        news_fetcher.fetch_all_news(), symbol
    )
    sentiment   = ai_analyzer.analyze_news_sentiment(symbol, symbol_news)
    prediction  = ai_analyzer.predict_probability(technical, sentiment)
    entry       = entry_strategy.suggest_entry(technical)

    # Phân tích chuyên sâu bổ sung (chỉ dùng cho /scan)
    deep = deep_analysis.run_deep_scan(symbol, df, technical, symbol_news)

    # Render báo cáo chuyên sâu
    report = deep_analysis.format_deep_report(symbol, technical, deep, entry, prediction)

    if send_telegram:
        telegram_notifier.send_message(report)
        logger.info("Đã gửi phân tích chuyên sâu %s qua Telegram.", symbol)
    else:
        print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot phân tích & cảnh báo chứng khoán Việt Nam")
    parser.add_argument("--scan", help="Phân tích nhanh 1 mã")
    parser.add_argument("--telegram", action="store_true", help="Gửi kết quả --scan về Telegram (dùng khi gọi từ GitHub Actions)")
    parser.add_argument("--no-telegram", action="store_true", help="Chỉ in báo cáo ra terminal, không gửi Telegram")
    parser.add_argument("--label", default=None, help="Nhãn hiển thị trên báo cáo")
    args = parser.parse_args()

    if args.scan:
        run_single_scan(args.scan, send_telegram=args.telegram)
    elif args.no_telegram:
        print(build_full_report(args.label or "Chạy thủ công"))
    else:
        run_full_report(args.label or "Chạy thủ công")
