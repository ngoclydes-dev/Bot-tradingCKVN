"""
data_fetcher.py
---------------
Lấy dữ liệu giá lịch sử cho các mã trên HOSE/HNX bằng thư viện `vnstock`
(nguồn dữ liệu tổng hợp từ VCI/TCBS/SSI - đang là lựa chọn phổ biến nhất
cho Python + chứng khoán Việt Nam, miễn phí, không cần API key).

Nếu vnstock đổi API hoặc nguồn dữ liệu lỗi, có thể thay thế hàm
get_stock_history() bằng nguồn khác (SSI iBoard, DNSE, TCBS API...) mà
không ảnh hưởng tới phần còn lại của bot.
"""
import logging
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_stock_history(symbol: str, days: int = 120) -> pd.DataFrame:
    """
    Trả về DataFrame lịch sử giá của 1 mã, đã chuẩn hoá cột:
    time, open, high, low, close, volume  (sắp xếp tăng dần theo thời gian)

    Ném exception nếu không lấy được dữ liệu - nơi gọi cần try/except.
    """
    from vnstock import Vnstock

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    # *2 vì lịch sử có ngày nghỉ/lễ, cần khoảng dư để đủ `days` phiên giao dịch

    stock = Vnstock().stock(symbol=symbol, source="VCI")
    df = stock.quote.history(start=start_date, end=end_date, interval="1D")

    if df is None or df.empty:
        raise ValueError(f"Không lấy được dữ liệu cho mã {symbol}")

    df = df.rename(columns={c: c.lower() for c in df.columns})
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dữ liệu mã {symbol} thiếu cột: {missing}")

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    # Chỉ giữ lại số phiên gần nhất cần dùng
    if len(df) > days:
        df = df.iloc[-days:].reset_index(drop=True)

    return df


def get_watchlist_history(symbols: list[str], days: int = 120) -> dict[str, pd.DataFrame]:
    """Lấy dữ liệu cho cả danh sách mã, bỏ qua mã nào lỗi (log lại để biết)."""
    result = {}
    for sym in symbols:
        try:
            result[sym] = get_stock_history(sym, days=days)
            logger.info("Đã lấy dữ liệu cho %s (%d phiên)", sym, len(result[sym]))
        except Exception as e:
            logger.warning("Lỗi khi lấy dữ liệu mã %s: %s", sym, e)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = get_stock_history("VNM", days=60)
    print(df.tail())
