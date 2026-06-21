"""
strategy.py — Port dari scanner_scalp.py (logic scoring TIDAK diubah).
Sumber asli: github.com/FakhrisGithub/scalp-scanner

Bedanya dari scanner asli:
- Tidak bergantung pada ws_price.py (live price websocket) — pakai REST price saja,
  karena untuk eksekusi otomatis kita re-fetch harga tepat sebelum order (bukan dari cache scan).
- News boost (CoinGecko + Fear&Greed) tetap dipakai tapi fail-safe: kalau gagal fetch, boost = 0.
- Tidak ada cetak/print untuk UI tabel — return dict bersih untuk dikonsumsi executor.
"""

import time
import urllib.request
import json
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import MACD


# ======================================
# NEWS & CATALYST (CoinGecko, fail-safe)
# ======================================

_news_cache = {"trending": [], "top_gainers": [], "fear_greed": 50, "fg_label": "Neutral", "last_fetch": 0}
NEWS_TTL = 300


def _fetch_json(url: str, timeout: int = 8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def refresh_news_cache():
    global _news_cache
    now = time.time()
    if now - _news_cache["last_fetch"] < NEWS_TTL:
        return
    try:
        data = _fetch_json("https://api.coingecko.com/api/v3/search/trending")
        trending = []
        if data and "coins" in data:
            for item in data["coins"]:
                sym = item.get("item", {}).get("symbol", "").upper()
                if sym:
                    trending.append(sym + "USDT")

        data2 = _fetch_json(
            "https://api.coingecko.com/api/v3/coins/markets"
            "?vs_currency=usd&order=price_change_percentage_24h_desc&per_page=50&page=1&sparkline=false"
        )
        top_gainers = []
        if isinstance(data2, list):
            for coin in data2:
                sym = coin.get("symbol", "").upper()
                if sym:
                    top_gainers.append(sym + "USDT")

        fg_data = _fetch_json("https://api.alternative.me/fng/?limit=1")
        fg_val, fg_label = 50, "Neutral"
        if fg_data and "data" in fg_data and fg_data["data"]:
            fg_val = int(fg_data["data"][0]["value"])
            fg_label = fg_data["data"][0]["value_classification"]

        _news_cache.update({
            "trending": trending, "top_gainers": top_gainers,
            "fear_greed": fg_val, "fg_label": fg_label, "last_fetch": now,
        })
    except Exception as e:
        print(f"[strategy] news cache refresh failed (non-fatal): {e}")


def get_news_boost(symbol: str) -> tuple:
    is_trending = symbol in _news_cache["trending"]
    is_gainer = symbol in _news_cache["top_gainers"]
    fg = _news_cache["fear_greed"]

    boost = 0
    labels = []
    if is_trending:
        boost += 10; labels.append("Trending")
    if is_gainer:
        boost += 8; labels.append("Gainer")
    if fg >= 75:
        boost += 5; labels.append("Greed")
    elif fg >= 60:
        boost += 2; labels.append("F&G+")
    elif fg <= 25:
        boost -= 5; labels.append("Fear")

    return boost, ",".join(labels) if labels else "-"


# ======================================
# INDICATORS (identik dengan scanner_scalp.py)
# ======================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]; high = df["high"]; low = df["low"]; vol = df["volume"]

    df["ema8"]   = close.ewm(span=8,   adjust=False).mean()
    df["ema20"]  = close.ewm(span=20,  adjust=False).mean()
    df["ema21"]  = close.ewm(span=21,  adjust=False).mean()
    df["ema50"]  = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    df["rsi"]    = RSIIndicator(close, window=14).rsi()
    df["rsi_ma"] = df["rsi"].rolling(9).mean()

    stoch = StochasticOscillator(high, low, close, window=14, smooth_window=3)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    macd_i = MACD(close, window_slow=26, window_fast=12, window_sign=9)
    df["macd"]        = macd_i.macd()
    df["macd_signal"] = macd_i.macd_signal()
    df["macd_hist"]   = macd_i.macd_diff()

    bb = BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, 1)

    df["atr"] = AverageTrueRange(high, low, close, window=14).average_true_range()

    df["vol_ma20"] = vol.rolling(20).mean()
    df["rel_vol"]  = vol / df["vol_ma20"].replace(0, 1)

    typical_price = (high + low + close) / 3
    cum_vol = vol.cumsum().replace(0, 1e-9)
    df["vwap"] = (typical_price * vol).cumsum() / cum_vol

    return df


# ======================================
# SIGNAL PER-TIMEFRAME (identik dengan scanner_scalp.py)
# ======================================

def scalp_signal_tf(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    prev = df.iloc[-2]

    price    = last["close"]
    ema8     = last["ema8"]
    ema20    = last["ema20"]
    ema21    = last["ema21"]
    ema50    = last["ema50"]
    ema200   = last["ema200"]
    vwap     = last["vwap"]
    rsi      = last["rsi"]
    stoch_k  = last["stoch_k"]
    stoch_d  = last["stoch_d"]
    macd_h   = last["macd_hist"]
    macd_h_p = prev["macd_hist"]
    bb_width = last["bb_width"]
    rel_vol  = last["rel_vol"]

    # ---- LONG ----
    lp, lc = 0, []
    if ema8 > ema21 > ema50:           lp += 20; lc.append("EMA↑")
    if price > ema8:                   lp += 10; lc.append("P>E8")
    if price > ema20:                  lp += 8;  lc.append("P>E20")
    if price > vwap:                   lp += 12; lc.append("P>VWAP")
    if price > ema200:                 lp += 8;  lc.append("P>E200")
    else:                              lp -= 5
    if 45 <= rsi <= 70:                lp += 10; lc.append(f"RSI{round(rsi)}")
    elif rsi > 70:                     lp +=  3
    if prev["stoch_k"] < prev["stoch_d"] and stoch_k > stoch_d and stoch_k < 80:
                                       lp += 15; lc.append("Stoch↑")
    elif stoch_k > stoch_d and stoch_k < 80: lp += 7; lc.append("Stoch+")
    if macd_h > 0 and macd_h_p <= 0:  lp += 20; lc.append("MACD✓")
    elif macd_h > macd_h_p:           lp +=  8; lc.append("MACD↑")
    if rel_vol >= 2.0:                 lp += 15; lc.append(f"RVol{round(rel_vol,1)}x")
    elif rel_vol >= 1.5:               lp += 10; lc.append(f"RVol{round(rel_vol,1)}x")
    elif rel_vol >= 1.2:               lp +=  5
    else:                              lp -=  8
    prev_bw = df["bb_width"].iloc[-5:-1].mean()
    if bb_width > prev_bw * 1.3 and price > last["bb_mid"]:
                                       lp += 10; lc.append("BB-Brk")

    # ---- SHORT ----
    sp, sc = 0, []
    if ema8 < ema21 < ema50:           sp += 20; sc.append("EMA↓")
    if price < ema8:                   sp += 10; sc.append("P<E8")
    if price < ema20:                  sp += 8;  sc.append("P<E20")
    if price < vwap:                   sp += 12; sc.append("P<VWAP")
    if price < ema200:                 sp += 8;  sc.append("P<E200")
    else:                              sp -= 5
    if 30 <= rsi <= 55:                sp += 10; sc.append(f"RSI{round(rsi)}")
    if prev["stoch_k"] > prev["stoch_d"] and stoch_k < stoch_d and stoch_k > 20:
                                       sp += 15; sc.append("Stoch↓")
    elif stoch_k < stoch_d and stoch_k > 20: sp += 7; sc.append("Stoch-")
    if macd_h < 0 and macd_h_p >= 0:  sp += 20; sc.append("MACD✗")
    elif macd_h < macd_h_p:           sp +=  8; sc.append("MACD↓")
    if rel_vol >= 2.0:                 sp += 15; sc.append(f"RVol{round(rel_vol,1)}x")
    elif rel_vol >= 1.5:               sp += 10; sc.append(f"RVol{round(rel_vol,1)}x")
    elif rel_vol >= 1.2:               sp +=  5
    else:                              sp -=  8
    if bb_width > prev_bw * 1.3 and price < last["bb_mid"]:
                                       sp += 10; sc.append("BB-Brk")

    lp = max(min(lp, 100), 0)
    sp = max(min(sp, 100), 0)

    if lp >= sp + 10:
        bias, pts, cond = "LONG", lp, ",".join(lc)
    elif sp >= lp + 10:
        bias, pts, cond = "SHORT", sp, ",".join(sc)
    else:
        bias, pts, cond = "FLAT", max(lp, sp), "-"

    return {
        "bias": bias, "score": pts, "long_pts": lp, "short_pts": sp,
        "rsi": round(rsi, 1), "stoch_k": round(stoch_k, 1), "rel_vol": round(rel_vol, 2),
        "vol_confirm": rel_vol >= 1.2, "atr": last["atr"], "price": price, "cond": cond,
        "ema20": round(ema20, 6), "ema200": round(ema200, 6), "vwap": round(vwap, 6),
        "above_ema200": price > ema200, "above_vwap": price > vwap,
    }


# ======================================
# ENTRY / SL / TP CALCULATOR (identik dengan scanner_scalp.py)
# ======================================

def scalp_entry(df5m: pd.DataFrame, bias: str, live_price: float = None, oi_chg_pct: float = 0.0) -> dict:
    last = df5m.iloc[-1]
    atr = last["atr"]
    price = live_price if (live_price and live_price > 0) else last["close"]

    oi_note = ""
    if bias == "LONG" and oi_chg_pct > 0.5:
        oi_note = " +OI"
    elif bias == "SHORT" and oi_chg_pct > 0.5:
        oi_note = " +OI"
    elif abs(oi_chg_pct) > 0.5:
        oi_note = " OI⚠"

    if bias == "LONG":
        entry = round(price, 6)
        sl  = round(price - atr * 1.0, 6)
        tp1 = round(price + atr * 1.5, 6)
        tp2 = round(price + atr * 2.5, 6)
    elif bias == "SHORT":
        entry = round(price, 6)
        sl  = round(price + atr * 1.0, 6)
        tp1 = round(price - atr * 1.5, 6)
        tp2 = round(price - atr * 2.5, 6)
    else:
        return {"entry": None, "sl": None, "tp1": None, "tp2": None, "entry_note": "No Setup"}

    rr1 = round(abs(tp1 - entry) / max(abs(entry - sl), 1e-12), 2)
    rr2 = round(abs(tp2 - entry) / max(abs(entry - sl), 1e-12), 2)
    note = ("Live" if (live_price and live_price > 0) else "REST-Fallback") + oi_note
    return {
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
        "rr1": rr1, "rr2": rr2, "entry_note": note,
    }


# ======================================
# CONFLUENCE SCORE & DECISION (identik dengan scanner_scalp.py)
# ======================================

def scalp_confluence(sig5m, sig15m, sig30m, sig1h, news_boost, oi_chg_pct: float = 0.0) -> dict:
    sigs = [sig5m, sig15m, sig30m, sig1h]

    long_v  = sum(1 for s in sigs if s["bias"] == "LONG")
    short_v = sum(1 for s in sigs if s["bias"] == "SHORT")

    if long_v >= 3:
        bias = "LONG"; vote_sc = long_v * 8
    elif short_v >= 3:
        bias = "SHORT"; vote_sc = short_v * 8
    elif long_v == 2 and sig1h["bias"] == "LONG":
        bias = "LONG"; vote_sc = 12
    elif short_v == 2 and sig1h["bias"] == "SHORT":
        bias = "SHORT"; vote_sc = 12
    else:
        bias = "FLAT"; vote_sc = 0

    if bias != "FLAT":
        weighted = (
            sig5m["score"]  * 0.10 +
            sig15m["score"] * 0.15 +
            sig30m["score"] * 0.40 +
            sig1h["score"]  * 0.35
        )
    else:
        weighted = 0

    vol_ok  = sig30m["rel_vol"] >= 1.3 or sig1h["rel_vol"] >= 1.3
    macd_ok = any("MACD✓" in s["cond"] or "MACD✗" in s["cond"] for s in sigs)

    oi_boost = 0
    if bias == "LONG" and oi_chg_pct > 0.5:
        oi_boost = 6
    elif bias == "SHORT" and oi_chg_pct > 0.5:
        oi_boost = 6
    elif abs(oi_chg_pct) > 1.5:
        oi_boost = -4

    if not vol_ok:  weighted *= 0.6
    if not macd_ok: weighted *= 0.8

    final = min(max(round(weighted + vote_sc + news_boost + oi_boost), 0), 100)

    if bias == "FLAT" or final < 62:
        decision = "SKIP"
    elif final >= 80 and vol_ok:
        decision = "SCALP_NOW" if bias == "LONG" else "SHORT_NOW"
    elif final >= 70:
        decision = "ENTRY" if bias == "LONG" else "SHORT"
    else:
        decision = "WATCH"

    if   final >= 85: grade = "A+"
    elif final >= 75: grade = "A"
    elif final >= 62: grade = "B"
    elif final >= 50: grade = "C"
    else:             grade = "D"

    return {
        "final": final, "bias": bias, "decision": decision, "grade": grade,
        "vol_ok": vol_ok, "macd_ok": macd_ok,
        "long_v": long_v, "short_v": short_v,
    }


# ======================================
# ANALYZE SYMBOL — entry point untuk dipanggil dari bot
# ======================================

def analyze_symbol(session, symbol: str) -> dict | None:
    """
    Analisa 1 simbol dengan 4 timeframe (5M, 15M, 30M, 1H) dan kembalikan
    dict berisi keputusan + entry/sl/tp. Return None kalau data tidak cukup
    atau terjadi error (di-skip oleh caller, bukan fatal).
    """
    try:
        def fetch_df(interval, limit=250):
            kline = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(
                kline["result"]["list"],
                columns=["time", "open", "high", "low", "close", "volume", "turnover"]
            )
            df = df[::-1].reset_index(drop=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            return df

        df5m  = add_indicators(fetch_df("5"))
        df15m = add_indicators(fetch_df("15"))
        df30m = add_indicators(fetch_df("30"))
        df1h  = add_indicators(fetch_df("60"))

        if len(df5m) < 50 or len(df15m) < 50 or len(df30m) < 50 or len(df1h) < 50:
            return None  # data historis belum cukup (simbol baru listing dll)

        sig5m  = scalp_signal_tf(df5m)
        sig15m = scalp_signal_tf(df15m)
        sig30m = scalp_signal_tf(df30m)
        sig1h  = scalp_signal_tf(df1h)

        news_boost, news_label = get_news_boost(symbol)

        # Open Interest
        try:
            oi_resp = session.get_open_interest(category="linear", symbol=symbol, intervalTime="5min", limit=2)
            oi_list = oi_resp.get("result", {}).get("list", [])
            if len(oi_list) >= 2:
                oi_now, oi_prev = float(oi_list[0]["openInterest"]), float(oi_list[1]["openInterest"])
                oi_chg_pct = ((oi_now - oi_prev) / oi_prev * 100) if oi_prev > 0 else 0.0
            else:
                oi_chg_pct = 0.0
        except Exception:
            oi_chg_pct = 0.0

        confluence = scalp_confluence(sig5m, sig15m, sig30m, sig1h, news_boost, oi_chg_pct)

        # Harga referensi untuk entry: ambil ticker REST terbaru (real-time saat keputusan diambil)
        ticker = session.get_tickers(category="linear", symbol=symbol)
        live_price = float(ticker["result"]["list"][0]["lastPrice"])

        entry = scalp_entry(df5m, confluence["bias"], live_price=live_price, oi_chg_pct=oi_chg_pct)

        return {
            "symbol": symbol,
            "final_score": confluence["final"],
            "bias": confluence["bias"],
            "decision": confluence["decision"],
            "grade": confluence["grade"],
            "vol_ok": confluence["vol_ok"],
            "news_label": news_label,
            "entry": entry["entry"],
            "sl": entry["sl"],
            "tp1": entry["tp1"],
            "tp2": entry["tp2"],
            "rr1": entry.get("rr1"),
            "live_price": live_price,
            "detail": {
                "5m": sig5m["cond"], "15m": sig15m["cond"],
                "30m": sig30m["cond"], "1h": sig1h["cond"],
            },
        }

    except Exception as e:
        print(f"[strategy] ERROR analyzing {symbol}: {e}")
        return None
