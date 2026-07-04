"""
deep_analysis.py
-----------------
Phân tích chuyên sâu cho lệnh /scan [MÃ] từ Telegram — chi tiết hơn
nhiều so với báo cáo hằng ngày, bao gồm:

1. Đa chỉ báo kỹ thuật: RSI, MACD, Bollinger Bands, Stochastic,
   MA5/MA20/MA50, Volume trend
2. Phân tích xu hướng đa khung thời gian (ngắn/trung/dài hạn)
3. Vùng hỗ trợ/kháng cự động
4. Đánh giá sức mạnh xu hướng (ADX)
5. Phân tích tin tức chuyên sâu bằng AI (narrative đầy đủ)
6. Đề xuất chiến lược giao dịch cụ thể (entry, SL, TP, sizing)
7. Cảnh báo rủi ro
"""
import logging
import json
import re
import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


# ===================== CÁC CHỈ BÁO BỔ SUNG =====================

def calculate_macd(df: pd.DataFrame,
                   fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD = EMA12 - EMA26, Signal = EMA9 của MACD, Histogram = MACD - Signal."""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    last_macd = float(macd_line.iloc[-1])
    last_signal = float(signal_line.iloc[-1])
    last_hist = float(histogram.iloc[-1])
    prev_hist = float(histogram.iloc[-2]) if len(histogram) > 1 else 0

    return {
        "macd": round(last_macd, 3),
        "signal": round(last_signal, 3),
        "histogram": round(last_hist, 3),
        "trend": "tăng" if last_macd > last_signal else "giảm",
        "momentum": "tăng tốc" if abs(last_hist) > abs(prev_hist) else "giảm tốc",
        "crossover": (
            "vừa cắt lên (bullish)" if last_hist > 0 and prev_hist <= 0 else
            "vừa cắt xuống (bearish)" if last_hist < 0 and prev_hist >= 0 else
            "chưa có crossover"
        ),
    }


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> dict:
    """Bollinger Bands: Upper/Middle/Lower và %B (vị trí giá trong dải)."""
    ma = df["close"].rolling(period).mean()
    sd = df["close"].rolling(period).std()
    upper = ma + std * sd
    lower = ma - std * sd

    last_close = float(df["close"].iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])
    last_ma    = float(ma.iloc[-1])
    band_width = last_upper - last_lower

    pct_b = (last_close - last_lower) / band_width if band_width > 0 else 0.5

    return {
        "upper": round(last_upper, 2),
        "middle": round(last_ma, 2),
        "lower": round(last_lower, 2),
        "pct_b": round(pct_b, 2),
        "band_width_pct": round(band_width / last_ma * 100, 2) if last_ma else 0,
        "position": (
            "trên upper band (quá mua)" if last_close > last_upper else
            "dưới lower band (quá bán)" if last_close < last_lower else
            "trong dải bình thường"
        ),
    }


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> dict:
    """Stochastic %K và %D — đo vị trí giá trong range N phiên."""
    low_n  = df["low"].rolling(k_period).min()
    high_n = df["high"].rolling(k_period).max()
    pct_k  = 100 * (df["close"] - low_n) / (high_n - low_n + 1e-9)
    pct_d  = pct_k.rolling(d_period).mean()

    last_k = float(pct_k.iloc[-1])
    last_d = float(pct_d.iloc[-1])

    return {
        "k": round(last_k, 1),
        "d": round(last_d, 1),
        "state": (
            "quá mua (>80)" if last_k > 80 else
            "quá bán (<20)" if last_k < 20 else
            "trung tính"
        ),
        "signal": "bullish" if last_k > last_d else "bearish",
    }


def calculate_adx(df: pd.DataFrame, period: int = 14) -> dict:
    """ADX — đo sức mạnh xu hướng (không phân biệt chiều tăng/giảm)."""
    high = df["high"]
    low  = df["low"]
    close = df["close"]

    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm[plus_dm < minus_dm]  = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr14    = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr14
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr14
    dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx      = dx.ewm(alpha=1/period, adjust=False).mean()

    last_adx      = float(adx.iloc[-1])
    last_plus_di  = float(plus_di.iloc[-1])
    last_minus_di = float(minus_di.iloc[-1])

    return {
        "adx": round(last_adx, 1),
        "plus_di": round(last_plus_di, 1),
        "minus_di": round(last_minus_di, 1),
        "strength": (
            "xu hướng rất mạnh" if last_adx > 50 else
            "xu hướng mạnh"     if last_adx > 25 else
            "xu hướng yếu / sideway" if last_adx > 15 else
            "không có xu hướng rõ"
        ),
        "direction": "tăng" if last_plus_di > last_minus_di else "giảm",
    }


def find_support_resistance(df: pd.DataFrame, lookback: int = 60) -> dict:
    """
    Tìm vùng hỗ trợ/kháng cự bằng cách xác định các đỉnh/đáy cục bộ
    trong N phiên gần nhất (dùng rolling window để tìm local extrema).
    """
    recent = df.tail(lookback).copy().reset_index(drop=True)
    last_close = float(df["close"].iloc[-1])

    # Tìm đỉnh cục bộ (kháng cự)
    highs = []
    for i in range(2, len(recent) - 2):
        if (recent["high"].iloc[i] > recent["high"].iloc[i-1] and
            recent["high"].iloc[i] > recent["high"].iloc[i-2] and
            recent["high"].iloc[i] > recent["high"].iloc[i+1] and
            recent["high"].iloc[i] > recent["high"].iloc[i+2]):
            highs.append(float(recent["high"].iloc[i]))

    # Tìm đáy cục bộ (hỗ trợ)
    lows = []
    for i in range(2, len(recent) - 2):
        if (recent["low"].iloc[i] < recent["low"].iloc[i-1] and
            recent["low"].iloc[i] < recent["low"].iloc[i-2] and
            recent["low"].iloc[i] < recent["low"].iloc[i+1] and
            recent["low"].iloc[i] < recent["low"].iloc[i+2]):
            lows.append(float(recent["low"].iloc[i]))

    # Lấy mức kháng cự gần nhất phía trên và hỗ trợ gần nhất phía dưới
    resistances = sorted([h for h in highs if h > last_close])[:3]
    supports    = sorted([l for l in lows  if l < last_close], reverse=True)[:3]

    return {
        "supports":    [round(s, 2) for s in supports],
        "resistances": [round(r, 2) for r in resistances],
        "nearest_support":    round(supports[0], 2)    if supports    else None,
        "nearest_resistance": round(resistances[0], 2) if resistances else None,
    }


def analyze_volume_trend(df: pd.DataFrame, period: int = 20) -> dict:
    """Phân tích xu hướng khối lượng giao dịch."""
    avg_vol = float(df["volume"].rolling(period).mean().iloc[-1])
    last_vol = float(df["volume"].iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol else 1

    # Tính trend volume 5 phiên gần nhất (tăng hay giảm dần)
    recent_vols = df["volume"].tail(5).values
    vol_trend = "tăng" if recent_vols[-1] > recent_vols[0] else "giảm"

    return {
        "last_volume": int(last_vol),
        "avg_volume_20": int(avg_vol),
        "vol_ratio": round(vol_ratio, 2),
        "vol_vs_avg": (
            f"gấp {vol_ratio:.1f}x TB20 — dòng tiền mạnh" if vol_ratio >= 1.5 else
            f"bằng {vol_ratio:.1f}x TB20 — bình thường"   if vol_ratio >= 0.8 else
            f"chỉ {vol_ratio:.1f}x TB20 — dòng tiền yếu"
        ),
        "trend_5_phien": vol_trend,
    }


def multi_timeframe_trend(df: pd.DataFrame) -> dict:
    """Phân tích xu hướng theo 3 khung: ngắn (5 phiên), trung (20 phiên), dài (60 phiên)."""
    close = df["close"]

    def trend_label(n):
        if len(close) < n + 1:
            return "chưa đủ dữ liệu"
        chg = (float(close.iloc[-1]) - float(close.iloc[-n])) / float(close.iloc[-n]) * 100
        if chg > 3:   return f"tăng mạnh (+{chg:.1f}%)"
        if chg > 0.5: return f"tăng nhẹ (+{chg:.1f}%)"
        if chg < -3:  return f"giảm mạnh ({chg:.1f}%)"
        if chg < -0.5: return f"giảm nhẹ ({chg:.1f}%)"
        return f"đi ngang ({chg:+.1f}%)"

    return {
        "ngan_han_5p":  trend_label(5),
        "trung_han_20p": trend_label(20),
        "dai_han_60p":  trend_label(60),
    }


# ===================== PHÂN TÍCH AI CHUYÊN SÂU =====================

def deep_ai_analysis(symbol: str, technical: dict, deep: dict,
                     news_items: list[dict]) -> str:
    """
    Dùng Claude API để viết nhận định chuyên sâu dạng narrative (đoạn văn),
    thay vì chỉ ra điểm số như báo cáo hằng ngày. Fallback về tóm tắt
    rule-based nếu không có API key.
    """
    if not config.ANTHROPIC_API_KEY:
        return _rule_based_narrative(symbol, technical, deep)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        news_text = "\n".join(
            f"- [{n['source']}] {n['title']}" for n in news_items[:8]
        ) if news_items else "Không có tin tức liên quan gần đây."

        prompt = f"""Bạn là chuyên gia phân tích kỹ thuật chứng khoán Việt Nam với 10 năm kinh nghiệm.
Dưới đây là dữ liệu phân tích đầy đủ của mã {symbol}:

**GIÁ & BIẾN ĐỘNG:**
- Giá hiện tại: {technical['last_close']:,} đ | Thay đổi: {technical['change_pct']:+.2f}%
- ATR(14): {technical['atr']:,} đ | Biến động/ngày trung bình

**ĐA CHỈ BÁO KỸ THUẬT:**
- RSI(14): {technical['rsi']} → {technical['rsi_state']}
- MACD: {deep['macd']['trend']}, {deep['macd']['crossover']}, momentum {deep['macd']['momentum']}
- Stochastic: %K={deep['stoch']['k']}, %D={deep['stoch']['d']} → {deep['stoch']['state']}
- Bollinger: {deep['bb']['position']}, %B={deep['bb']['pct_b']}
- ADX(14): {deep['adx']['adx']} → {deep['adx']['strength']}, hướng {deep['adx']['direction']}

**XU HƯỚNG ĐA KHUNG:**
- Ngắn hạn (5 phiên): {deep['mtf']['ngan_han_5p']}
- Trung hạn (20 phiên): {deep['mtf']['trung_han_20p']}
- Dài hạn (60 phiên): {deep['mtf']['dai_han_60p']}

**KHỐI LƯỢNG:**
- {deep['volume']['vol_vs_avg']}
- Trend 5 phiên: {deep['volume']['trend_5_phien']}

**HỖ TRỢ/KHÁNG CỰ:**
- Hỗ trợ gần nhất: {deep['sr']['nearest_support']:,} đ
- Kháng cự gần nhất: {deep['sr']['nearest_resistance']:,} đ

**TIN TỨC GẦN ĐÂY:**
{news_text}

Hãy viết nhận định phân tích chuyên sâu bằng tiếng Việt, gồm 3 phần ngắn gọn:
1. **Bức tranh tổng thể** (2-3 câu về xu hướng hiện tại và sức mạnh)
2. **Tín hiệu nổi bật** (điểm mạnh/yếu kỹ thuật cần chú ý nhất)
3. **Khuyến nghị ngắn hạn** (nên theo dõi/chờ/vào hay tránh, với lý do cụ thể)

Viết thực tế, khách quan, không hoa mỹ. Tối đa 150 từ."""

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

    except Exception as e:
        logger.warning("Lỗi AI deep analysis, dùng rule-based: %s", e)
        return _rule_based_narrative(symbol, technical, deep)


def _rule_based_narrative(symbol: str, technical: dict, deep: dict) -> str:
    """Nhận định tổng hợp không cần AI — dùng khi không có API key."""
    adx = deep["adx"]
    macd = deep["macd"]
    mtf = deep["mtf"]

    lines = []

    # Bức tranh tổng thể
    trend_strength = adx["strength"]
    trend_dir = adx["direction"]
    lines.append(f"📌 *Tổng thể:* {symbol} đang trong xu hướng *{trend_dir}* với {trend_strength}. "
                 f"Trung hạn 20 phiên {mtf['trung_han_20p']}, dài hạn 60 phiên {mtf['dai_han_60p']}.")

    # Tín hiệu nổi bật
    signals = []
    if technical["rsi"] <= config.RSI_OVERSOLD:
        signals.append("RSI quá bán → tiềm năng hồi phục")
    elif technical["rsi"] >= config.RSI_OVERBOUGHT:
        signals.append("RSI quá mua → cẩn thận điều chỉnh")
    if "cắt lên" in macd["crossover"]:
        signals.append("MACD vừa cắt lên → tín hiệu mua")
    elif "cắt xuống" in macd["crossover"]:
        signals.append("MACD vừa cắt xuống → tín hiệu bán")
    if deep["bb"]["pct_b"] < 0.1:
        signals.append("Giá chạm lower Bollinger → vùng quá bán")
    elif deep["bb"]["pct_b"] > 0.9:
        signals.append("Giá chạm upper Bollinger → vùng quá mua")
    if deep["volume"]["vol_ratio"] >= 1.5:
        signals.append(f"Volume đột biến {deep['volume']['vol_ratio']}x TB → dòng tiền vào mạnh")

    if signals:
        lines.append("⚡ *Tín hiệu:* " + " | ".join(signals[:3]))
    else:
        lines.append("⚡ *Tín hiệu:* Chưa có tín hiệu kỹ thuật đặc biệt nổi bật.")

    return "\n".join(lines)


# ===================== HÀM TỔNG HỢP CHÍNH =====================

def run_deep_scan(symbol: str, df: pd.DataFrame,
                  technical: dict, news_items: list[dict]) -> dict:
    """
    Chạy toàn bộ phân tích chuyên sâu cho 1 mã.
    Trả về dict đầy đủ để format_deep_report() render thành tin nhắn Telegram.
    """
    import multi_ai

    deep = {
        "macd":   calculate_macd(df),
        "bb":     calculate_bollinger(df),
        "stoch":  calculate_stochastic(df),
        "adx":    calculate_adx(df),
        "sr":     find_support_resistance(df),
        "volume": analyze_volume_trend(df),
        "mtf":    multi_timeframe_trend(df),
    }

    # Gọi đa AI song song (có thể thất bại do rate limit, không crash)
    try:
        deep["multi_ai"] = multi_ai.analyze_multi_ai(symbol, technical, deep, news_items)
    except Exception as e:
        logger.warning("multi_ai.analyze_multi_ai loi: %s", e)
        deep["multi_ai"] = {
            "available_ais": [],
            "gemini_result": None,
            "error": f"Loi bat ngo: {str(e)[:100]}",
        }
    return deep


def _fmt_price(value: float) -> str:
    """
    Format giá thông minh:
    - Giá >= 1000 (đã nhân 1000, đơn vị đồng thực): dùng dấu phẩy, không số lẻ
      VD: 15200 -> "15,200"
    - Giá < 1000 (dữ liệu vnstock trả về đơn vị nghìn đồng):
      nhân 1000 rồi hiển thị
      VD: 15.2 -> "15,200"
    Luôn hiển thị giá thực tế theo đơn vị đồng VN để dễ đọc.
    """
    # vnstock trả về giá đơn vị nghìn đồng (VD: 15.2 = 15,200đ)
    # Nhân 1000 nếu giá < 1000 để hiển thị đúng
    real = value * 1000 if value < 1000 else value
    return f"{real:,.0f}"


def _fmt_atr(value: float) -> str:
    """ATR cũng cần nhân 1000 nếu dữ liệu đơn vị nghìn đồng."""
    real = value * 1000 if value < 1000 else value
    if real < 100:
        return f"{real:,.1f}"
    return f"{real:,.0f}"


def format_deep_report(symbol: str, technical: dict, deep: dict,
                       entry: dict, prediction: dict) -> str:
    """
    Render toàn bộ kết quả phân tích sâu thành tin nhắn Telegram Markdown.
    """
    import multi_ai as multi_ai_module
    t  = technical
    d  = deep
    p  = prediction
    sr = d["sr"]

    change_icon = "📈" if t["change_pct"] >= 0 else "📉"

    lines = [
        f"🔬 *PHÂN TÍCH CHUYÊN SÂU: {symbol}*",
        f"{'─' * 30}",

        # ── Giá & tổng quan ──
        f"💰 *Giá:* {_fmt_price(t['last_close'])} đ  {change_icon} {t['change_pct']:+.2f}%",
        f"📊 *Xác suất tăng giá:* {p['probability_up_pct']}% — {p['label']}",
        "",

        # ── Đa chỉ báo ──
        "📐 *CHỈ BÁO KỸ THUẬT*",
        f"• RSI(14): *{t['rsi']}* → {t['rsi_state']}",
        f"• MACD: {d['macd']['trend']} | {d['macd']['crossover']} | momentum {d['macd']['momentum']}",
        f"• Stochastic: %K={d['stoch']['k']} %D={d['stoch']['d']} → {d['stoch']['state']} ({d['stoch']['signal']})",
        f"• Bollinger: {d['bb']['position']} | %B={d['bb']['pct_b']}",
        f"• ADX(14): {d['adx']['adx']} → {d['adx']['strength']}",
        f"• MA20: {_fmt_price(t['ma20'])} đ | Xu hướng: {t['ma_trend']}",
        "",

        # ── Xu hướng đa khung ──
        "⏱ *XU HƯỚNG ĐA KHUNG*",
        f"• Ngắn hạn (5 phiên): {d['mtf']['ngan_han_5p']}",
        f"• Trung hạn (20 phiên): {d['mtf']['trung_han_20p']}",
        f"• Dài hạn (60 phiên): {d['mtf']['dai_han_60p']}",
        "",

        # ── Hỗ trợ / Kháng cự ──
        "🎯 *HỖ TRỢ / KHÁNG CỰ*",
    ]

    if sr["resistances"]:
        lines.append("• Kháng cự: " + " → ".join(_fmt_price(r) for r in sr["resistances"]) + " đ")
    if sr["supports"]:
        lines.append("• Hỗ trợ:   " + " → ".join(_fmt_price(s) for s in sr["supports"]) + " đ")

    lines += [
        "",

        # ── Volume ──
        "📦 *KHỐI LƯỢNG GIAO DỊCH*",
        f"• {d['volume']['vol_vs_avg']}",
        f"• Trend 5 phiên: {d['volume']['trend_5_phien']} | ATR(14): {_fmt_atr(t['atr'])} đ",
        "",

        # ── Nhận định đa AI ──
        multi_ai_module.format_multi_ai_block(d["multi_ai"]),
        "",

        # ── Chiến lược vào lệnh ──
        "💡 *CHIẾN LƯỢC VÀO LỆNH*",
    ]

    # Entry block
    if entry["entry_low"] is not None:
        lines += [
            f"• Setup: {entry['setup']}",
            f"• Vùng vào: {_fmt_price(entry['entry_low'])} — {_fmt_price(entry['entry_high'])} đ",
            f"• Dừng lỗ: {_fmt_price(entry['stop_loss'])} đ",
        ]
        if entry["take_profit"]:
            rr_text = f" (R:R ≈ 1:{entry['risk_reward']})" if entry["risk_reward"] else ""
            lines.append(f"• Chốt lời: {_fmt_price(entry['take_profit'])} đ{rr_text}")
        lines.append(f"• _{entry['note']}_")
    else:
        lines.append(f"• _{entry['note']}_")

    lines += [
        "",
        "⚠️ _Đây là phân tích kỹ thuật tham khảo, không phải khuyến nghị đầu tư._",
    ]

    return "\n".join(lines)
