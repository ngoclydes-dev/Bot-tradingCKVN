"""
data_fetcher.py
---------------
Lấy dữ liệu giá lịch sử HOSE/HNX qua Yahoo Finance (yfinance).

Cổ phiếu Việt Nam trên Yahoo Finance dùng suffix:
  - HOSE: VNM.VN, VCB.VN, FPT.VN ...
  - HNX: PVS.HN, SHB.HN ...

Hoàn toàn miễn phí, không cần API key, GitHub Actions truy cập được bình thường.
"""
import logging
import warnings
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Suffix mặc định — hầu hết cổ phiếu lớn HOSE dùng .VN
# Nếu mã không tìm thấy trên .VN, tự động thử .HN (HNX)
_SUFFIX_ORDER = [".VN", ".HN"]


def _fetch_yfinance(ticker_str: str, days: int) -> pd.DataFrame | None:
    """Tải dữ liệu từ Yahoo Finance, trả về DataFrame chuẩn hoặc None nếu lỗi."""
    try:
        import yfinance as yf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ticker = yf.Ticker(ticker_str)
            df = ticker.history(
                period=f"{days}d",
                interval="1d",
                auto_adjust=True,
                repair=False,
            )

        if df is None or df.empty:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Chuẩn hoá cột
        rename = {}
        for col in df.columns:
            if col in ("date",):
                rename[col] = "time"
        df = df.rename(columns=rename)

        if "time" not in df.columns:
            return None

        df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)

        required = {"time", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None

        df = df[list(required)].sort_values("time").reset_index(drop=True)
        return df

    except Exception as e:
        logger.debug("yfinance %s lỗi: %s", ticker_str, e)
        return None


def get_stock_history(symbol: str, days: int = 120) -> pd.DataFrame:
    """
    Lấy lịch sử giá cho 1 mã. Tự động thử suffix .VN rồi .HN.
    Ném ValueError nếu không lấy được dữ liệu.
    """
    # Thêm buffer ngày để bù ngày nghỉ/lễ
    fetch_days = days + 40

    for suffix in _SUFFIX_ORDER:
        ticker_str = f"{symbol.upper()}{suffix}"
        df = _fetch_yfinance(ticker_str, fetch_days)
        if df is not None and len(df) >= 10:
            logger.info("Đã lấy %d phiên cho %s (%s)", len(df), symbol, ticker_str)
            # Chỉ giữ số phiên cần dùng
            if len(df) > days:
                df = df.iloc[-days:].reset_index(drop=True)
            return df

    raise ValueError(
        f"Không lấy được dữ liệu cho mã {symbol} "
        f"(đã thử: {', '.join(symbol + s for s in _SUFFIX_ORDER)}). "
        f"Kiểm tra lại mã có đúng không."
    )


def get_watchlist_history(symbols: list[str], days: int = 120) -> dict[str, pd.DataFrame]:
    """Lấy dữ liệu cho cả danh sách mã, bỏ qua mã nào lỗi."""
    result = {}
    for sym in symbols:
        try:
            result[sym] = get_stock_history(sym, days=days)
        except Exception as e:
            logger.warning("Bỏ qua %s: %s", sym, e)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = get_stock_history("VNM", days=60)
    print(df.tail(5))
