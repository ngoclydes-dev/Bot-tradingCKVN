"""
entry_strategy.py
-------------------
Đề xuất ĐIỂM VÀO (entry), ĐIỂM DỪNG LỖ (stop-loss) và ĐIỂM CHỐT LỜI
(take-profit) dựa trên setup kỹ thuật hiện tại của mã, theo 3 kịch bản
phổ biến nhất khi trade theo breakout/trend:

1. BREAKOUT      — giá đã vượt kháng cự kèm volume xác nhận
                   -> vào ngay theo breakout, dừng lỗ dưới mức kháng cự
                      vừa bị phá (giờ là hỗ trợ), target theo R:R.
2. PULLBACK MA20 — xu hướng tăng, giá đang test lại MA20 (không quá xa)
                   -> vào khi giá hồi về MA20, dừng lỗ dưới MA20 1 khoảng
                      ATR, target = vùng kháng cự gần nhất.
3. HỒI PHỤC QUÁ BÁN — RSI quá bán, giá gần đáy ngắn hạn
                   -> vào thận trọng, dừng lỗ dưới đáy gần nhất, target
                      = MA20 (mức hồi phục kỹ thuật hợp lý).

Nếu không khớp kịch bản nào rõ ràng (VD: RSI quá mua, xu hướng giảm,
giá nằm giữa vùng không có tín hiệu) -> KHÔNG đề xuất điểm vào, khuyến
nghị đứng ngoài quan sát.

QUAN TRỌNG: đây là gợi ý dựa trên quy tắc kỹ thuật phổ biến (rule-based),
KHÔNG phải khuyến nghị đầu tư được kiểm chứng. Luôn tự quản trị rủi ro
và không vào lệnh vượt quá khả năng chịu rủi ro của bản thân.
"""
import config


def _round_price(x: float) -> float:
    return round(float(x), 2)


def suggest_entry(technical: dict) -> dict:
    """
    technical: kết quả từ indicators.analyze_symbol()
    Trả về dict:
        {
            "setup": str,                # tên kịch bản, hoặc "Không có setup"
            "entry_low": float | None,
            "entry_high": float | None,
            "stop_loss": float | None,
            "take_profit": float | None,
            "risk_reward": float | None, # tỷ lệ Reward/Risk
            "note": str,
        }
    """
    atr = technical["atr"] or 0
    last_close = technical["last_close"]
    ma20 = technical["ma20"]
    rsi = technical["rsi"]
    breakout = technical["breakout"]
    recent_low = technical["recent_low_20"]
    resistance_60 = technical.get("resistance_60")

    atr_mult = config.STOP_LOSS_ATR_MULTIPLIER
    rr_target = config.RISK_REWARD_TARGET

    empty = {
        "setup": "Không có setup rõ ràng",
        "entry_low": None, "entry_high": None,
        "stop_loss": None, "take_profit": None,
        "risk_reward": None,
        "note": "Chưa có tín hiệu kỹ thuật đủ rõ để đề xuất điểm vào — nên đứng ngoài quan sát.",
    }

    # --- Kịch bản 1: BREAKOUT ---
    if breakout.get("is_breakout"):
        entry_low = breakout["resistance_level"]
        entry_high = _round_price(last_close * 1.01)  # cho phép mua đuổi tối đa +1%
        stop_loss = _round_price(breakout["resistance_level"] - atr_mult * atr)
        risk = entry_low - stop_loss
        take_profit = _round_price(entry_low + rr_target * risk) if risk > 0 else None
        rr = round(rr_target, 2) if risk > 0 else None
        return {
            "setup": "🚀 Breakout — vào theo đà phá kháng cự",
            "entry_low": _round_price(entry_low),
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": rr,
            "note": "Ưu tiên vào ngay phiên breakout hoặc phiên test lại kháng cự cũ (hỗ trợ mới) "
                    "với volume vẫn duy trì tốt.",
        }

    # --- Kịch bản 2: PULLBACK VỀ MA20 (xu hướng tăng) ---
    if technical["ma_trend"] == "tăng" and rsi < config.RSI_OVERBOUGHT:
        distance_pct = abs(last_close - ma20) / ma20 * 100 if ma20 else 999
        if distance_pct <= config.PULLBACK_MAX_DISTANCE_PCT:
            entry_low = _round_price(ma20 * 0.99)
            entry_high = _round_price(ma20 * 1.015)
            stop_loss = _round_price(ma20 - atr_mult * atr)
            risk = entry_low - stop_loss
            if resistance_60 and resistance_60 > entry_high:
                take_profit = _round_price(resistance_60)
            else:
                take_profit = _round_price(entry_low + rr_target * risk) if risk > 0 else None
            rr = (
                round((take_profit - entry_low) / risk, 2)
                if (risk and risk > 0 and take_profit) else None
            )
            return {
                "setup": "📈 Pullback MA20 — mua khi giá hồi về vùng hỗ trợ MA20",
                "entry_low": entry_low,
                "entry_high": entry_high,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward": rr,
                "note": "Chờ giá về gần MA20 và xác nhận giữ vững (không xuyên thủng kèm volume bán mạnh) "
                        "trước khi vào, tránh bắt dao khi MA20 bị phá.",
            }

    # --- Kịch bản 3: HỒI PHỤC TỪ QUÁ BÁN ---
    if rsi <= config.RSI_OVERSOLD:
        entry_low = _round_price(last_close * 0.995)
        entry_high = _round_price(last_close * 1.01)
        stop_loss = _round_price(recent_low - 0.5 * atr)
        risk = entry_low - stop_loss
        take_profit = _round_price(ma20) if ma20 and ma20 > entry_high else (
            _round_price(entry_low + rr_target * risk) if risk > 0 else None
        )
        rr = (
            round((take_profit - entry_low) / risk, 2)
            if (risk and risk > 0 and take_profit) else None
        )
        return {
            "setup": "🔄 Hồi phục kỹ thuật từ vùng quá bán",
            "entry_low": entry_low,
            "entry_high": entry_high,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": rr,
            "note": "Đây là lệnh đánh hồi ngắn hạn, rủi ro cao hơn 2 kịch bản trên — nên giảm khối lượng "
                    "và tuân thủ chặt điểm dừng lỗ.",
        }

    return empty


def format_entry_block(entry: dict) -> str:
    """Format kết quả suggest_entry() thành đoạn text Markdown cho Telegram."""
    if entry["entry_low"] is None:
        return f"💡 Điểm vào: _{entry['note']}_"

    lines = [
        f"💡 *Setup: {entry['setup']}*",
        f"Vùng vào: {entry['entry_low']:,.0f} — {entry['entry_high']:,.0f} đ",
    ]
    if entry["stop_loss"] is not None:
        lines.append(f"Dừng lỗ: {entry['stop_loss']:,.0f} đ")
    if entry["take_profit"] is not None:
        lines.append(f"Chốt lời: {entry['take_profit']:,.0f} đ"
                      + (f" (R:R ≈ 1:{entry['risk_reward']})" if entry["risk_reward"] else ""))
    lines.append(f"_{entry['note']}_")
    return "\n".join(lines)
