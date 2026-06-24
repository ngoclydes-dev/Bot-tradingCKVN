# Bot Tín Hiệu Chứng Khoán Việt Nam (HOSE/HNX) → Telegram

Bot Python tự động phân tích kỹ thuật, đọc tin tức, dùng AI dự đoán xác suất
tăng giá và gửi báo cáo qua Telegram 2 lần/ngày (8h00 & 15h00) hoặc chạy thủ công.

## Luồng xử lý

```
Python
  ↓
Lấy dữ liệu giá HOSE/HNX (vnstock)
  ↓
Tính RSI(14)
  ↓
Tính MA20 + xu hướng
  ↓
Phát hiện Breakout (giá vượt kháng cự N phiên + volume xác nhận)
  ↓
Lấy tin tức (RSS: CafeF, Vietstock, NDH...)
  ↓
Phân tích AI tin tức (Claude API, fallback rule-based nếu không có key)
  ↓
Tính xác suất tăng giá (kết hợp RSI + MA + Breakout + Sentiment tin tức)
  ↓
Gửi tín hiệu/báo cáo qua Telegram
```

## Cấu trúc project

```
(repo root)
├── .github/workflows/
│   ├── daily-report.yml    # GitHub Actions: báo cáo 8h00 & 15h00
│   └── realtime-scan.yml   # GitHub Actions: quét breakout mỗi 15 phút
├── config.py              # Cấu hình: watchlist, tham số kỹ thuật, trọng số AI, phiên giao dịch
├── data_fetcher.py        # Lấy dữ liệu giá HOSE/HNX qua vnstock
├── indicators.py           # RSI, MA20, breakout detection
├── news_fetcher.py         # Lấy tin tức từ RSS chứng khoán VN
├── ai_analyzer.py          # Phân tích sentiment AI + tính xác suất tăng giá
├── telegram_notifier.py    # Gửi tin nhắn Telegram
├── market_hours.py         # Kiểm tra có đang trong phiên giao dịch HOSE/HNX không
├── state_store.py          # Lưu trạng thái đã cảnh báo (chống gửi trùng)
├── realtime_alert.py       # Quét breakout nhanh trong giờ giao dịch, gửi cảnh báo tức thì
├── main.py                  # Điều phối toàn bộ pipeline, chạy báo cáo đầy đủ
├── scheduler.py             # (Chỉ dùng cho Cách B) chạy nền liên tục trên máy/VPS riêng
├── state/breakout_state.json  # Trạng thái chống gửi trùng (GitHub Actions tự commit lại)
├── requirements.txt
└── .env.example
```

## 🚀 Cách A (khuyến nghị): Chạy hoàn toàn bằng GitHub Actions — KHÔNG cần bật máy

Repo này đã có sẵn 2 workflow trong `.github/workflows/`, chạy theo lịch (cron) trên server
miễn phí của GitHub, không cần máy/VPS riêng nào chạy 24/7.

| Workflow | Lịch chạy (giờ Việt Nam) | Việc làm |
|---|---|---|
| `daily-report.yml` | 08:00 & 15:00 (Mon-Fri) | Gửi báo cáo đầy đủ toàn watchlist + AI + tin tức + xác suất |
| `realtime-scan.yml` | Mỗi 15 phút trong giờ giao dịch (9h15-11h30, 13h00-14h45) | Quét nhanh, gửi cảnh báo ngay khi có breakout mới |

### Bước 1 — Đẩy code lên GitHub

```bash
git init
git add .
git commit -m "init: vn stock bot"
git branch -M main
git remote add origin https://github.com/<ten-tai-khoan>/<ten-repo>.git
git push -u origin main
```

### Bước 2 — Khai báo Secrets (KHÔNG dùng file .env trên GitHub)

Vào repo trên GitHub → **Settings → Secrets and variables → Actions → New repository secret**,
tạo các secret sau (lấy giá trị giống như khi điền vào `.env` ở phần hướng dẫn dưới):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY` (tùy chọn, để trống nếu không dùng AI thật)

### Bước 3 — Cấp quyền ghi cho Actions (để bot tự lưu trạng thái chống gửi trùng)

Vào **Settings → Actions → General → Workflow permissions** → chọn
**"Read and write permissions"** → Save.
(Cần bước này vì `realtime-scan.yml` tự commit lại file `state/breakout_state.json` sau mỗi lần quét.)

### Bước 4 — Kiểm tra hoạt động

Vào tab **Actions** trên GitHub → chọn workflow → bấm **"Run workflow"** để chạy thử ngay
(không cần đợi đến giờ) → kiểm tra Telegram có nhận được tin không.

### Lưu ý khi dùng GitHub Actions

- Lịch chạy theo cron của GitHub **có thể trễ vài phút** so với giờ đặt, đặc biệt lúc hệ thống
  GitHub tải cao — đây là giới hạn chung của GitHub Actions schedule, không phải lỗi code.
- Nếu repo **không có hoạt động (commit/chạy) trong 60 ngày liên tục**, GitHub sẽ tự tắt các
  workflow theo lịch — chỉ cần vào tab Actions bấm enable lại.
- Repo **public**: miễn phí không giới hạn phút chạy. Repo **private**: có hạn mức phút/tháng
  miễn phí (đủ dùng cho bot này vì mỗi lần chạy chỉ mất ~30-60 giây).

---

## Cách B — Chạy trên máy/VPS riêng (scheduler.py hoặc cron nội bộ)

Dùng cách này nếu bạn muốn tự kiểm soát server, debug dễ hơn, hoặc không muốn phụ thuộc GitHub.

### 1. Cài đặt

```bash
# (đã ở sẵn trong thư mục repo sau khi git clone)
python3 -m venv venv && source venv/bin/activate   # khuyến nghị dùng venv
pip install -r requirements.txt
cp .env.example .env
```

### 2. Lấy thông tin Telegram

1. Mở Telegram, chat với **@BotFather** → gõ `/newbot` → đặt tên → nhận `TELEGRAM_BOT_TOKEN`.
2. Lấy `chat_id`:
   - Nhận tín hiệu cho **cá nhân**: chat với **@userinfobot**, nó trả về ID của bạn.
   - Nhận tín hiệu cho **group/channel**: thêm bot vào group, gửi 1 tin nhắn bất kỳ trong group,
     rồi mở `https://api.telegram.org/bot<TOKEN>/getUpdates` trên trình duyệt để lấy `chat.id`
     (thường là số âm, ví dụ `-100123456789`).
3. Điền `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` vào file `.env`.

### 3. (Tùy chọn) Bật phân tích AI bằng Claude

- Lấy API key tại [console.anthropic.com](https://console.anthropic.com), điền vào
  `ANTHROPIC_API_KEY` trong `.env`.
- Nếu **không** điền key, bot vẫn chạy bình thường, chỉ chuyển sang chấm điểm tin tức
  theo từ khoá (rule-based) thay vì dùng AI đọc hiểu ngữ cảnh.

### 4. Tùy chỉnh danh sách mã & tham số kỹ thuật

Sửa trong `config.py`:
- `WATCHLIST`: danh sách mã cần theo dõi (HOSE/HNX).
- `RSI_PERIOD`, `RSI_OVERBOUGHT/OVERSOLD`, `MA_PERIOD`.
- `BREAKOUT_LOOKBACK`, `BREAKOUT_VOLUME_MULTIPLIER`: độ nhạy phát hiện breakout.
- `NEWS_RSS_FEEDS`: thêm/bớt nguồn tin RSS.
- `WEIGHTS`: trọng số kết hợp các tín hiệu khi tính xác suất tăng giá (tổng nên = 1.0).

### 5. Chạy thử

```bash
# Phân tích nhanh 1 mã, in ra terminal (không gửi Telegram) - dùng để test trước
python main.py --scan VNM

# Chạy full report 1 lần, in ra terminal, KHÔNG gửi Telegram
python main.py --no-telegram

# Chạy full report 1 lần và GỬI Telegram thật
python main.py
```

### 6. Chạy tự động lúc 8h00 & 15h00 hàng ngày + cảnh báo Breakout Real-time

#### B1 — dùng scheduler.py có sẵn (đơn giản, phù hợp VPS/máy luôn mở)

```bash
python scheduler.py
```

Khi chạy, scheduler sẽ tự động đăng ký **3 loại job**:
1. Báo cáo đầy đủ lúc **8h00** (toàn bộ watchlist + AI + tin tức + xác suất).
2. Báo cáo đầy đủ lúc **15h00**.
3. **Quét breakout real-time mỗi 15 phút** (`config.REALTIME_SCAN_INTERVAL_MINUTES`) trong giờ
   giao dịch (`config.TRADING_SESSIONS`, mặc định 9h15-11h30 và 13h00-14h45). Job này chỉ gửi
   Telegram khi phát hiện **breakout mới** và mã đó **chưa được cảnh báo trong ngày** (tránh spam
   lặp lại mỗi 15 phút) — trạng thái lưu tại `state/breakout_state.json`.

Tiến trình sẽ chạy nền liên tục (Mon-Fri, theo giờ Việt Nam). Để giữ tiến trình sống lâu dài, nên
chạy qua `systemd`, `pm2`, `tmux`/`screen`, hoặc Docker.

Ví dụ chạy nền bằng `nohup`:
```bash
nohup python scheduler.py > bot.log 2>&1 &
```

Test thử cảnh báo real-time ngay lập tức (bỏ qua kiểm tra giờ giao dịch):
```bash
python realtime_alert.py --force
```

#### B2 — dùng cron của hệ điều hành (khuyến nghị nếu chạy trên server riêng, ổn định hơn B1)

```bash
crontab -e
```
Thêm các dòng sau (đường dẫn venv/repo tùy máy bạn):
```
# Báo cáo đầy đủ 8h00 & 15h00
0 8 * * 1-5  cd /duong/dan/repo && /duong/dan/venv/bin/python main.py >> bot.log 2>&1
0 15 * * 1-5 cd /duong/dan/repo && /duong/dan/venv/bin/python main.py >> bot.log 2>&1

# Quét breakout real-time mỗi 15 phút trong giờ hành chính (script tự lọc đúng giờ giao dịch)
*/15 8-15 * * 1-5 cd /duong/dan/repo && /duong/dan/venv/bin/python realtime_alert.py >> realtime.log 2>&1
```

## Lưu ý quan trọng

- **Nguồn dữ liệu**: bot dùng thư viện `vnstock` (tổng hợp từ VCI/TCBS), miễn phí và không cần
  đăng ký API key, nhưng đây là dữ liệu công khai phi chính thức — nếu nguồn đổi cấu trúc, chỉ cần
  sửa `data_fetcher.py`, các phần khác không bị ảnh hưởng.
- **Xác suất tăng giá** là chỉ số tổng hợp heuristic (RSI + MA20 + Breakout + Sentiment tin tức
  theo trọng số bạn tự cấu hình), **không phải** mô hình thống kê/ML được kiểm chứng và **không
  phải lời khuyên đầu tư**. Nên dùng làm 1 tín hiệu tham khảo trong nhiều nguồn thông tin.
- Tin tức lấy qua RSS công khai — nếu một nguồn nào đó ngừng cung cấp RSS hoặc đổi URL, chỉ cần
  cập nhật `config.NEWS_RSS_FEEDS`.
- Khi mở rộng watchlist lớn, để ý **rate limit** của nguồn dữ liệu (vnstock) — có thể cần thêm
  `time.sleep()` giữa các lần gọi nếu bị chặn tạm thời.

## Mở rộng thêm (gợi ý)

- Lưu lịch sử tín hiệu vào SQLite/CSV để sau này đánh giá độ chính xác của mô hình xác suất.
- Thêm chỉ báo khác (MACD, Bollinger Bands) vào `indicators.py` và `config.WEIGHTS`.
- Thêm lệnh `/start`, `/watchlist`, `/scan VNM` để biến bot thành Telegram Bot 2 chiều
  (hiện tại chỉ gửi 1 chiều qua Bot API, chưa nhận lệnh từ người dùng).
