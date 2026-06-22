"""
config.py — Semua parameter bot diatur di sini.
Ubah nilai-nilai ini sesuai kebutuhan, JANGAN ubah logic di file lain
kalau cuma mau tuning angka.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ======================================
# API CREDENTIALS (dari .env, JANGAN hardcode di sini)
# ======================================
API_KEY    = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")

# Bybit punya 3 environment terpisah, masing-masing butuh API key sendiri:
#   - Production (mainnet asli)         -> testnet=False, demo=False
#   - Demo Trading (akun demo di mainnet UI, saldo dummy 50rb USDT) -> testnet=False, demo=True
#   - Testnet murni (testnet.bybit.com, tanpa toggle Demo Trading)  -> testnet=True,  demo=False
# Key dari satu environment TIDAK BISA dipakai di environment lain (akan selalu error 10003).
BYBIT_MODE = os.getenv("BYBIT_MODE", "demo").lower()   # "demo" | "testnet" | "live"

TESTNET = BYBIT_MODE == "testnet"
DEMO    = BYBIT_MODE == "demo"
LIVE    = BYBIT_MODE == "live"

# Safety lock tambahan KHUSUS untuk live — uang sungguhan. Bot menolak start kalau
# BYBIT_MODE=live tapi ini belum di-set eksplisit ke "YES_I_UNDERSTAND_THE_RISK".
# Ini supaya transisi ke live tidak terjadi cuma gara-gara salah ganti 1 variable
# tanpa kamu benar-benar sadar.
LIVE_CONFIRM = os.getenv("LIVE_CONFIRM", "")

# ======================================
# SCAN SETTINGS
# ======================================
SCAN_INTERVAL_SECONDS = 300       # interval scan ulang semua simbol (default 5 menit)
MAX_WORKERS            = 10       # thread parallel untuk fetch data. Kalau deploy di Railway
                                   # hobby plan (RAM kecil), jangan dinaikkan terlalu jauh — bisa OOM
                                   # saat scan ratusan simbol sekaligus.

# ======================================
# ENTRY FILTER
# ======================================
MIN_SCORE_TO_ENTRY = 80           # hanya entry kalau final score >= ini (SCALP NOW / SHORT NOW)
REQUIRE_VOL_OK      = True        # wajib rel_vol >= 1.3 di 30M atau 1H (sama seperti decision asli)

# ======================================
# POSITION SIZING & LEVERAGE
# ======================================
# Default berbeda per mode: live sengaja jauh lebih konservatif daripada testnet/demo,
# supaya kesalahan konfigurasi tidak langsung jadi kerugian besar di uang asli.
# Override lewat .env kapan saja kalau sudah yakin (lihat MARGIN_PER_TRADE_USDT_LIVE dst).
if LIVE:
    MARGIN_PER_TRADE_USDT    = float(os.getenv("MARGIN_PER_TRADE_USDT_LIVE", "5.0"))
    LEVERAGE                 = int(os.getenv("LEVERAGE_LIVE", "10"))
    MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS_LIVE", "1"))
else:
    MARGIN_PER_TRADE_USDT    = 10.0
    LEVERAGE                 = 10
    MAX_CONCURRENT_POSITIONS = 3

# ======================================
# EXIT RULES
# ======================================
USE_TP1_ONLY        = True         # True = full close di TP1 (sesuai keputusan kamu)
TIME_EXIT_MINUTES   = 45           # kalau belum kena TP/SL dalam X menit, close manual (anti "nyangkut")

# ======================================
# RISK MANAGEMENT (circuit breaker)
# ======================================
# Live pakai limit jauh lebih ketat secara default — circuit breaker yang lebih cepat
# menahan bot itu jauh lebih murah daripada kerugian beruntun yang tidak tertahan.
if LIVE:
    DAILY_LOSS_LIMIT_PCT     = float(os.getenv("DAILY_LOSS_LIMIT_PCT_LIVE", "2.5"))
    MAX_CONSECUTIVE_LOSSES   = int(os.getenv("MAX_CONSECUTIVE_LOSSES_LIVE", "3"))
    PAUSE_AFTER_MAX_LOSS_MIN = int(os.getenv("PAUSE_AFTER_MAX_LOSS_MIN_LIVE", "240"))
else:
    DAILY_LOSS_LIMIT_PCT     = 5.0
    MAX_CONSECUTIVE_LOSSES   = 4
    PAUSE_AFTER_MAX_LOSS_MIN = 120

# ======================================
# SYMBOL FILTER (opsional)
# ======================================
EXCLUDE_SYMBOLS = []                # contoh: ["1000PEPEUSDT"] kalau mau exclude simbol tertentu

# Testnet/demo punya volume trading jauh lebih kecil dari mainnet asli (uang dummy),
# jadi threshold turnover yang masuk akal untuk live ($1M) akan membuang hampir semua
# simbol di testnet. Pakai threshold rendah untuk testnet/demo, threshold realistis untuk live.
MIN_TURNOVER_24H_USDT = 1_000_000.0 if LIVE else 1_000.0

# ======================================
# LOGGING
# ======================================
LOG_FILE = "bot_trades.csv"         # semua entry/exit dicatat ke sini untuk evaluasi nanti
