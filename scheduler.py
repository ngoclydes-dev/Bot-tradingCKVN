"""
scheduler.py
------------
Chạy bot ở chế độ nền (daemon), tự động gửi báo cáo Telegram vào các
thời điểm cấu hình trong config.REPORT_TIMES (mặc định 8h00 và 15h00,
giờ Việt Nam - Asia/Ho_Chi_Minh).

Chạy:
    python scheduler.py

Khuyến nghị deploy thực tế: dùng systemd / pm2 / Docker để giữ tiến
trình này luôn sống, hoặc thay scheduler bằng cron job gọi
`python main.py` đúng 2 mốc giờ (xem README.md mục "Triển khai thực tế").
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import main as bot_main
import realtime_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")


def job_morning():
    logger.info("Bắt đầu chạy báo cáo SÁNG (8h00)")
    bot_main.run_full_report("Báo cáo SÁNG (08:00)")


def job_afternoon():
    logger.info("Bắt đầu chạy báo cáo CHIỀU (15h00)")
    bot_main.run_full_report("Báo cáo CHIỀU (15:00)")


def job_realtime_scan():
    # Job này được lên lịch chạy mỗi N phút suốt cả ngày (mon-fri); bản thân
    # run_realtime_scan() sẽ tự kiểm tra có đang trong phiên giao dịch hay
    # không (qua market_hours.is_trading_session) để bỏ qua giờ nghỉ trưa,
    # trước/sau giờ giao dịch mà không cần cấu hình cron phức tạp.
    realtime_alert.run_realtime_scan()


def main():
    scheduler = BlockingScheduler(timezone=config.TIMEZONE)

    jobs = [job_morning, job_afternoon]
    for job_fn, time_cfg in zip(jobs, config.REPORT_TIMES):
        scheduler.add_job(
            job_fn,
            trigger=CronTrigger(
                hour=time_cfg["hour"],
                minute=time_cfg["minute"],
                day_of_week="mon-fri",  # chỉ chạy ngày giao dịch (thứ 2 - thứ 6)
                timezone=config.TIMEZONE,
            ),
            id=job_fn.__name__,
        )
        logger.info(
            "Đã đăng ký job '%s' lúc %02d:%02d (Mon-Fri, %s)",
            job_fn.__name__, time_cfg["hour"], time_cfg["minute"], config.TIMEZONE,
        )

    # Job quét breakout real-time: chạy mỗi N phút suốt cả ngày (mon-fri).
    # Việc lọc đúng giờ giao dịch (bỏ giờ nghỉ trưa, ngoài giờ) do
    # market_hours.is_trading_session() xử lý bên trong run_realtime_scan().
    scheduler.add_job(
        job_realtime_scan,
        trigger=CronTrigger(
            minute=f"*/{config.REALTIME_SCAN_INTERVAL_MINUTES}",
            day_of_week="mon-fri",
            timezone=config.TIMEZONE,
        ),
        id="job_realtime_scan",
    )
    logger.info(
        "Đã đăng ký job quét breakout real-time mỗi %d phút (Mon-Fri, trong các phiên: %s)",
        config.REALTIME_SCAN_INTERVAL_MINUTES,
        ", ".join(f"{s['start']}-{s['end']}" for s in config.TRADING_SESSIONS),
    )

    logger.info("Scheduler đang chạy... (Ctrl+C để dừng)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Đã dừng scheduler.")


if __name__ == "__main__":
    main()
