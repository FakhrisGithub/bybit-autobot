"""
executor.py — Eksekusi order ke Bybit berdasarkan sinyal dari strategy.py,
dengan sizing & leverage sesuai config.py.

PENTING: kode ini akan benar-benar mengirim order ke akun yang terhubung
ke API_KEY/API_SECRET di .env. Pastikan TESTNET=true sampai kamu yakin
hasil testnet konsisten dengan ekspektasi sebelum ganti ke live.
"""

import math
import config


def get_wallet_balance_usdt(session) -> float:
    resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    try:
        coin_list = resp["result"]["list"][0]["coin"]
        for c in coin_list:
            if c["coin"] == "USDT":
                return float(c["walletBalance"])
        return 0.0
    except (KeyError, IndexError):
        return 0.0


def get_instrument_filters(session, symbol: str) -> dict:
    """Ambil qtyStep dan minOrderQty supaya order tidak ditolak exchange karena presisi salah."""
    resp = session.get_instruments_info(category="linear", symbol=symbol)
    info = resp["result"]["list"][0]
    lot_filter = info["lotSizeFilter"]
    return {
        "qty_step": float(lot_filter["qtyStep"]),
        "min_qty": float(lot_filter["minOrderQty"]),
        "tick_size": float(info["priceFilter"]["tickSize"]),
    }


def round_step(value: float, step: float) -> float:
    if step == 0:
        return value
    precision = max(0, str(step)[::-1].find('.'))
    return round(math.floor(value / step) * step, precision)


def set_leverage(session, symbol: str, leverage: int):
    try:
        session.set_leverage(
            category="linear", symbol=symbol,
            buyLeverage=str(leverage), sellLeverage=str(leverage),
        )
    except Exception as e:
        # Bybit akan error kalau leverage sudah sama persis dengan yang diminta — itu aman, abaikan
        if "leverage not modified" not in str(e).lower():
            print(f"[executor] set_leverage warning for {symbol}: {e}")


def calc_qty(margin_usdt: float, leverage: int, price: float, qty_step: float, min_qty: float) -> float:
    notional = margin_usdt * leverage
    raw_qty = notional / price
    qty = round_step(raw_qty, qty_step)
    return max(qty, min_qty) if qty > 0 else 0.0


def open_position(session, signal: dict) -> dict | None:
    """
    signal: dict hasil dari strategy.analyze_symbol()
    Return dict berisi detail eksekusi, atau None kalau gagal/skip.
    """
    symbol = signal["symbol"]
    side = "Buy" if signal["bias"] == "LONG" else "Sell"

    try:
        filters = get_instrument_filters(session, symbol)
    except Exception as e:
        print(f"[executor] Gagal ambil filter instrumen {symbol}: {e}")
        return None

    set_leverage(session, symbol, config.LEVERAGE)

    qty = calc_qty(
        config.MARGIN_PER_TRADE_USDT, config.LEVERAGE, signal["entry"],
        filters["qty_step"], filters["min_qty"]
    )
    if qty <= 0:
        print(f"[executor] Qty terhitung 0 untuk {symbol}, skip.")
        return None

    sl_price = round_step(signal["sl"], filters["tick_size"])
    tp_price = round_step(signal["tp1"], filters["tick_size"])  # USE_TP1_ONLY = full close di TP1

    try:
        order = session.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            stopLoss=str(sl_price),
            takeProfit=str(tp_price),
            tpslMode="Full",
            positionIdx=0,  # one-way mode
        )
    except Exception as e:
        print(f"[executor] Gagal place_order {symbol}: {e}")
        return None

    if order.get("retCode") != 0:
        print(f"[executor] Order rejected {symbol}: {order.get('retMsg')}")
        return None

    print(f"[executor] OPEN {side} {symbol} qty={qty} entry~{signal['entry']} "
          f"SL={sl_price} TP={tp_price} score={signal['final_score']}")

    return {
        "symbol": symbol, "side": side, "qty": qty,
        "entry_price": signal["entry"], "sl": sl_price, "tp1": tp_price,
        "order_id": order["result"].get("orderId"),
    }


def close_position_market(session, symbol: str, side: str, qty: float) -> bool:
    """Force-close posisi via market order (dipakai untuk time-based exit)."""
    close_side = "Sell" if side == "Buy" else "Buy"
    try:
        order = session.place_order(
            category="linear", symbol=symbol, side=close_side,
            orderType="Market", qty=str(qty), reduceOnly=True, positionIdx=0,
        )
        return order.get("retCode") == 0
    except Exception as e:
        print(f"[executor] Gagal force-close {symbol}: {e}")
        return False


def get_open_position_info(session, symbol: str) -> dict | None:
    """Cek status posisi terkini di exchange (sumber kebenaran, bukan cuma state lokal)."""
    try:
        resp = session.get_positions(category="linear", symbol=symbol)
        lst = resp["result"]["list"]
        for p in lst:
            if float(p.get("size", 0)) > 0:
                return {
                    "symbol": symbol, "side": p["side"], "size": float(p["size"]),
                    "entry_price": float(p["avgPrice"]), "unrealized_pnl": float(p["unrealisedPnl"]),
                    "mark_price": float(p["markPrice"]),
                }
        return None
    except Exception as e:
        print(f"[executor] Gagal cek posisi {symbol}: {e}")
        return None
