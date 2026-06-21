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
MARGIN_PER_TRADE_USDT = 10.0       # margin (bukan notional) per posisi, dalam USDT
LEVERAGE               = 10        # leverage tetap, jauh lebih rendah dari kebiasaan manual (25-50x)
MAX_CONCURRENT_POSITIONS = 3       # maksimum posisi terbuka bersamaan

# ======================================
# EXIT RULES
# ======================================
USE_TP1_ONLY        = True         # True = full close di TP1 (sesuai keputusan kamu)
TIME_EXIT_MINUTES   = 45           # kalau belum kena TP/SL dalam X menit, close manual (anti "nyangkut")

# ======================================
# RISK MANAGEMENT (circuit breaker)
# ======================================
DAILY_LOSS_LIMIT_PCT     = 5.0     # bot auto-stop (tidak entry baru) kalau rugi harian >= 5% dari balance awal hari
MAX_CONSECUTIVE_LOSSES   = 4       # bot pause kalau kalah beruntun N kali
PAUSE_AFTER_MAX_LOSS_MIN = 120     # lama pause (menit) setelah kena max consecutive loss

# ======================================
# SYMBOL FILTER (opsional)
# ======================================
EXCLUDE_SYMBOLS = []                # contoh: ["1000PEPEUSDT"] kalau mau exclude simbol tertentu
MIN_TURNOVER_24H_USDT = 1_000_000   # skip simbol dengan turnover 24h terlalu kecil (likuiditas rendah = slippage besar)

# ======================================
# LOGGING
# ======================================
LOG_FILE = "bot_trades.csv"         # semua entry/exit dicatat ke sini untuk evaluasi nanti
