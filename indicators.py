"""
indicators.py
-------------
Tính các chỉ báo kỹ thuật: RSI, MA20, và phát hiện breakout (giá vượt
kháng cự kèm volume xác nhận). Mỗi hàm nhận vào 1 DataFrame OHLCV
(cột: time, open, high, low, close, volume) và trả về kết quả tương ứng.
"""
import pandas as pd
import numpy as np

import config


def calculate_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.Series:
    """RSI theo phương pháp Wilder's smoothing (chuẩn dùng trong các nền tảng phân tích)."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)  # giai đoạn chưa đủ dữ liệu -> coi như trung tính
    return rsi


def calculate_ma(df: pd.DataFrame, period: int = config.MA_PERIOD) -> pd.Series:
    """Đường trung bình động đơn giản (SMA)."""
    return df["close"].rolling(window=period, min_periods=1).mean()


def detect_breakout(df: pd.DataFrame,
                     lookback: int = config.BREAKOUT_LOOKBACK,
                     volume_mult: float = config.BREAKOUT_VOLUME_MULTIPLIER) -> dict:
    """
    Breakout = giá đóng cửa phiên gần nhất VƯỢT mức cao nhất của
    `lookback` phiên trước đó, kèm volume phiên đó >= volume_mult x
    volume trung bình `lookback` phiên.

    Trả về dict: {is_breakout, resistance_level, last_close, volume_ratio}
    """
    if len(df) < lookback + 1:
        return {"is_breakout": False, "resistance_level": None,
                "last_close": float(df["close"].iloc[-1]) if len(df) else None,
                "volume_ratio": None}

    prior = df.iloc[-(lookback + 1):-1]   # lookback phiên TRƯỚC phiên hiện tại
    last_row = df.iloc[-1]

    resistance_level = prior["high"].max()
    avg_volume = prior["volume"].mean()
    volume_ratio = (last_row["volume"] / avg_volume) if avg_volume else 0

    is_breakout = bool(
        last_row["close"] > resistance_level and volume_ratio >= volume_mult
    )

    return {
        "is_breakout": is_breakout,
        "resistance_level": round(float(resistance_level), 2),
        "last_close": round(float(last_row["close"]), 2),
        "volume_ratio": round(float(volume_ratio), 2),
    }


def analyze_symbol(df: pd.DataFrame) -> dict:
    """
    Tổng hợp toàn bộ chỉ báo kỹ thuật cho 1 mã -> dict gọn để dùng tiếp
    cho AI analyzer / Telegram message.
    """
    df = df.copy()
    df["rsi"] = calculate_rsi(df)
    df["ma20"] = calculate_ma(df)

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    breakout = detect_breakout(df)

    # Xu hướng theo MA20: giá trên MA20 và MA20 đang dốc lên -> tăng
    ma_slope = last["ma20"] - df["ma20"].iloc[max(0, len(df) - 6)]
    ma_trend = "tăng" if (last["close"] > last["ma20"] and ma_slope > 0) else (
        "giảm" if (last["close"] < last["ma20"] and ma_slope < 0) else "đi ngang"
    )

    rsi_state = (
        "quá mua" if last["rsi"] >= config.RSI_OVERBOUGHT else
        "quá bán" if last["rsi"] <= config.RSI_OVERSOLD else
        "trung tính"
    )

    return {
        "last_close": round(float(last["close"]), 2),
        "prev_close": round(float(prev["close"]), 2),
        "change_pct": round(float((last["close"] - prev["close"]) / prev["close"] * 100), 2)
        if prev["close"] else 0.0,
        "rsi": round(float(last["rsi"]), 1),
        "rsi_state": rsi_state,
        "ma20": round(float(last["ma20"]), 2),
        "ma_trend": ma_trend,
        "breakout": breakout,
        "volume": int(last["volume"]),
    }
