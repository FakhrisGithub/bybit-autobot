"""
bot.py — Main loop. Jalankan file ini untuk start bot.

Alur tiap siklus:
1. Cek apakah boleh entry baru (risk manager: daily loss limit, max concurrent, pause)
2. Cek posisi terbuka yang butuh time-based exit
3. Scan semua simbol USDT, analisa pakai strategy.py
4. Filter sinyal sesuai threshold (config.MIN_SCORE_TO_ENTRY)
5. Eksekusi entry untuk sinyal yang lolos (sampai MAX_CONCURRENT_POSITIONS)
6. Sleep sampai siklus berikutnya
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from pybit.unified_trading import HTTP

import config
import strategy
import executor
from risk_manager import RiskManager


def get_all_usdt_symbols(session) -> list:
    info = session.get_instruments_info(category="linear")
    symbols = []
    for x in info["result"]["list"]:
        sym = x["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym in config.EXCLUDE_SYMBOLS:
            continue
        symbols.append(sym)
    return symbols


def filter_by_turnover(session, symbols: list) -> list:
    """Buang simbol dengan turnover 24h terlalu kecil (likuiditas rendah)."""
    try:
        resp = session.get_tickers(category="linear")
        turnover_map = {t["symbol"]: float(t.get("turnover24h", 0) or 0) for t in resp["result"]["list"]}
        return [s for s in symbols if turnover_map.get(s, 0) >= config.MIN_TURNOVER_24H_USDT]
    except Exception as e:
        print(f"[bot] Gagal filter turnover, pakai semua simbol: {e}")
        return symbols


def scan_all(session, symbols: list) -> list:
    """Scan semua simbol secara paralel, return list sinyal yang valid (bukan None)."""
    results = []
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
        futures = {ex.submit(strategy.analyze_symbol, session, s): s for s in symbols}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception as e:
                sym = futures[f]
                print(f"[bot] Error analyzing {sym}: {e}")
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


def handle_time_exits(session, risk: RiskManager):
    symbols_to_exit = risk.positions_needing_time_exit()
    for symbol in symbols_to_exit:
        pos_info = executor.get_open_position_info(session, symbol)
        if not pos_info:
            # Posisi sudah tertutup duluan (kena SL/TP), bersihkan state lokal
            risk.open_positions.pop(symbol, None)
            continue

        print(f"[bot] Time exit triggered for {symbol} (>{config.TIME_EXIT_MINUTES} min belum kena TP/SL)")
        ok = executor.close_position_market(session, symbol, pos_info["side"], pos_info["size"])
        if ok:
            risk.register_close(
                symbol, pos_info["mark_price"], pos_info["unrealized_pnl"], "TIME_EXIT"
            )


def sync_closed_positions(session, risk: RiskManager):
    """Cek posisi yang tercatat lokal tapi sudah tertutup di exchange (kena SL/TP), update state."""
    for symbol in list(risk.open_positions.keys()):
        pos_info = executor.get_open_position_info(session, symbol)
        if not pos_info:
            # Sudah closed di exchange (SL atau TP kena), tapi kita tidak tahu pnl pasti tanpa
            # cek closed-pnl endpoint. Untuk simplicity, tandai closed dengan pnl 0 placeholder
            # dan biarkan log detail diisi manual dari riwayat Bybit kalau perlu presisi penuh.
            try:
                pnl_resp = session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
                pnl_list = pnl_resp["result"]["list"]
                pnl = float(pnl_list[0]["closedPnl"]) if pnl_list else 0.0
                exit_price = float(pnl_list[0]["avgExitPrice"]) if pnl_list else 0.0
            except Exception:
                pnl, exit_price = 0.0, 0.0
            risk.register_close(symbol, exit_price, pnl, "SL_OR_TP")


def run_cycle(session, risk: RiskManager):
    balance = executor.get_wallet_balance_usdt(session)
    print(f"\n[bot] === Cycle start | Balance: {balance:.2f} USDT | Open: {len(risk.open_positions)} ===")

    sync_closed_positions(session, risk)
    handle_time_exits(session, risk)

    can_open, reason = risk.can_open_new_position(balance)
    if not can_open:
        print(f"[bot] Skip new entries: {reason}")
        return

    symbols = get_all_usdt_symbols(session)
    symbols = filter_by_turnover(session, symbols)
    print(f"[bot] Scanning {len(symbols)} symbols...")

    signals = scan_all(session, symbols)

    qualified = [
        s for s in signals
        if s["final_score"] >= config.MIN_SCORE_TO_ENTRY
        and s["decision"] in ("SCALP_NOW", "SHORT_NOW")
        and (not config.REQUIRE_VOL_OK or s["vol_ok"])
        and not risk.is_symbol_open(s["symbol"])
    ]

    print(f"[bot] {len(qualified)} sinyal qualified (score>={config.MIN_SCORE_TO_ENTRY})")
    for s in qualified[:5]:
        print(f"       {s['symbol']:12s} {s['bias']:5s} score={s['final_score']} grade={s['grade']}")

    slots_available = config.MAX_CONCURRENT_POSITIONS - len(risk.open_positions)
    for signal in qualified[:slots_available]:
        can_open, reason = risk.can_open_new_position(balance)
        if not can_open:
            print(f"[bot] Stop entering more: {reason}")
            break

        result = executor.open_position(session, signal)
        if result:
            risk.register_open(
                result["symbol"], result["side"], result["entry_price"],
                result["sl"], result["tp1"]
            )


def main():
    if not config.API_KEY or not config.API_SECRET:
        raise SystemExit("BYBIT_API_KEY / BYBIT_API_SECRET belum diset di .env")

    session = HTTP(testnet=config.TESTNET, api_key=config.API_KEY, api_secret=config.API_SECRET)
    risk = RiskManager()

    print(f"[bot] Starting. TESTNET={config.TESTNET} | "
          f"MIN_SCORE={config.MIN_SCORE_TO_ENTRY} | LEVERAGE={config.LEVERAGE}x | "
          f"MARGIN/trade={config.MARGIN_PER_TRADE_USDT} USDT | "
          f"MAX_CONCURRENT={config.MAX_CONCURRENT_POSITIONS}")

    while True:
        try:
            run_cycle(session, risk)
        except Exception as e:
            print(f"[bot] FATAL error in cycle (continuing): {e}")
            traceback.print_exc()

        print(f"[bot] Sleeping {config.SCAN_INTERVAL_SECONDS}s...")
        time.sleep(config.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
