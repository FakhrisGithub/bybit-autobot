# Bybit Auto Trading Bot — berbasis scalp-scanner kamu

Port dari logic `scanner_scalp.py` (github.com/FakhrisGithub/scalp-scanner)
menjadi bot full-auto eksekusi, dengan tambahan risk management yang scanner
aslinya tidak punya (karena scanner aslinya cuma rekomendasi, bukan eksekusi).

## ⚠️ WAJIB DIBACA SEBELUM JALANKAN

1. **Mulai dari TESTNET.** `.env` default `BYBIT_TESTNET=true`. Jangan ganti
   ke `false` sebelum kamu run minimal beberapa hari di testnet dan paham
   betul perilaku bot-nya (kapan entry, kapan exit, kenapa).
2. Bot ini **full-auto** — begitu dijalankan, dia entry, pasang SL/TP, dan
   exit sendiri tanpa konfirmasi kamu tiap trade. Pastikan semua angka di
   `config.py` sudah sesuai keinginan SEBELUM start.
3. Strategi (scoring) di `strategy.py` adalah port 1:1 dari scanner kamu —
   **belum pernah di-backtest secara historis** lewat proses ini. Win rate
   ≥80% di nama variabel itu target desain, bukan hasil terverifikasi.
   Jalankan testnet cukup lama (saran: minimal 2 minggu / puluhan trade)
   sebelum percaya angka tersebut.

## Setup

```bash
cd bybit-autobot
pip install -r requirements.txt --break-system-packages

cp .env.example .env
# edit .env, isi BYBIT_API_KEY dan BYBIT_API_SECRET dari testnet.bybit.com
```

## Konfigurasi (`config.py`)

Semua parameter ada di satu file ini. Yang paling penting buat dicek dulu:

| Parameter | Default | Catatan |
|---|---|---|
| `MIN_SCORE_TO_ENTRY` | 80 | Threshold final score. Saran: jangan turunin sebelum ada data testnet. |
| `MARGIN_PER_TRADE_USDT` | 10.0 | Margin (bukan notional) per posisi. |
| `LEVERAGE` | 10 | Jauh lebih rendah dari kebiasaan manual kamu (25-50x) — sengaja, karena bot tidak bisa "rasa" market. |
| `MAX_CONCURRENT_POSITIONS` | 3 | Maks posisi terbuka bersamaan. |
| `TIME_EXIT_MINUTES` | 45 | Force-close kalau belum kena TP/SL dalam X menit. |
| `DAILY_LOSS_LIMIT_PCT` | 5.0 | Bot stop entry baru kalau rugi harian tembus ini. |
| `MAX_CONSECUTIVE_LOSSES` | 4 | Bot pause kalau kalah beruntun segini. |
| `SCAN_INTERVAL_SECONDS` | 300 | Interval scan ulang semua simbol USDT. |

## Menjalankan

```bash
python3 bot.py
```

Bot akan jalan terus (loop) sampai kamu hentikan manual (Ctrl+C). Setiap
entry/exit dicatat ke `bot_trades.csv` — file ini sumber evaluasi performa
kamu nanti (hitung win rate aktual, average R, dll).

## Struktur file

- `config.py` — semua parameter, ubah di sini kalau mau tuning
- `strategy.py` — logic scoring (port dari scanner_scalp.py kamu, TIDAK diubah)
- `risk_manager.py` — circuit breaker: daily loss limit, max consecutive loss, position limit
- `executor.py` — eksekusi order ke Bybit (place order, set leverage, force-close)
- `bot.py` — main loop yang menyatukan semua

## Yang BELUM ada (kamu bisa minta saya tambahkan setelah testnet jalan)

- Notifikasi Telegram/Discord tiap entry-exit
- Dashboard web untuk monitoring real-time (mirip CustomTkinter scanner kamu)
- Backtesting engine pakai data historis (sangat disarankan sebelum live)
- Auto-restart kalau bot crash (pakai systemd / supervisor / pm2)
- Reconciliation lebih presisi untuk closed PnL (saat ini ambil dari `get_closed_pnl`,
  cukup akurat tapi belum di-cross-check dengan funding fee dsb)

## Troubleshooting awal

- **"BYBIT_API_KEY belum diset"** → cek `.env` sudah diisi dan ada di folder yang sama dengan `bot.py`
- **Order rejected / leverage error** → biasanya karena testnet kadang reset data, atau simbol tidak available di testnet (tidak semua simbol live ada di testnet)
- **Qty terhitung 0** → margin terlalu kecil dibanding harga coin (coin mahal seperti BTC butuh margin lebih besar untuk capai min qty)
