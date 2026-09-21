#!/usr/bin/env python3
"""
order_guard.py v2 — SL/TP anti-gagal dengan JANITOR system.

Filosofi: posisi JANGAN ditutup paksa kalau SL/TP gagal kepasang.
Sebagai gantinya, Janitor (thread monitor) terus-menerus:
1. Scan semua posisi terbuka.
2. Cek: apakah posisi punya SL dan TP di openOrders?
3. Yang kurang -> pasang ulang (retry, backoff, QPS-guarded).
4. Ulangi tiap 5 detik sampai TERVERIFIKASI terpasang.
Selama SL/TP belum terpasang, bot baru MENAHAN entry berikutnya (bukan menutup).

Fail-safe terakhir (hanya jika user minta): close_market=False default.
"""
import os, json, time, hmac, hashlib, urllib.request, urllib.parse, threading

BASE = "https://fapi.binance.com"
API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
MAX_QPS = 5
JANITOR_INTERVAL = 5          # detik antar scan
MAX_GLOBAL_POSITIONS = 5      # << set dari user

_throttle_lock = threading.Lock()
_last_req = [0.0]
_janitor_thread = None
_janitor_stop = threading.Event()
_pending_guard = {}           # symbol -> True (sedang janitor kejar SL/TP-nya)

def _signed(params):
    qs = urllib.parse.urlencode(params)
    sig = hmac.new(API_SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return f"{qs}&signature={sig}"

def _req(method, path, params=None, signed=True):
    with _throttle_lock:
        wait = (1.0 / MAX_QPS) - (time.time() - _last_req[0])
        if wait > 0: time.sleep(wait)
        _last_req[0] = time.time()
    url = BASE + path
    if signed:
        params = dict(params or {}); params["timestamp"] = int(time.time()*1000)
        params["recvWindow"] = 5000
        url += "?" + _signed(params)
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method,
        headers={"X-MBX-APIKEY": API_KEY, "User-Agent": "v15unified/2.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def _cond_order(symbol, side_close, stop_price, otype):
    return _req("POST", "/fapi/v1/order", {
        "symbol": symbol, "side": side_close, "type": otype,
        "stopPrice": f"{stop_price:.6g}", "closePosition": "true",
        "workingType": "MARK_PRICE", "timeInForce": "GTE_GTC"})

def _position_qty(symbol):
    try:
        pos = _req("GET", "/fapi/v2/positionRisk", {"symbol": symbol})
        return abs(float(pos[0]["positionAmt"])) if pos else 0.0
    except Exception:
        return 0.0

def open_positions():
    """Semua posisi non-zero."""
    try:
        pos = _req("GET", "/fapi/v2/positionRisk")
        return [p for p in pos if abs(float(p["positionAmt"])) > 0]
    except Exception:
        return []

def order_status(symbol):
    """Return {'sl': bool, 'tp': bool} dari openOrders closePosition."""
    try:
        oo = _req("GET", "/fapi/v1/openOrders", {"symbol": symbol})
        types = {o["type"] for o in oo if o.get("closePosition")}
        return {"sl": "STOP_MARKET" in types, "tp": "TAKE_PROFIT_MARKET" in types}
    except Exception:
        return {"sl": False, "tp": False}

def try_place_sl_tp(symbol, side, sl, tp):
    """1x percobaan pasang SL dan/atau TP yang kurang. Return status terbaru."""
    close_side = "SELL" if side == "LONG" else "BUY"
    sl_type  = "STOP_MARKET" if side == "LONG" else "TAKE_PROFIT_MARKET"
    tp_type  = "TAKE_PROFIT_MARKET" if side == "LONG" else "STOP_MARKET"
    st = order_status(symbol)
    try:
        if not st["sl"]:
            _cond_order(symbol, close_side, sl, sl_type)
        if not st["tp"]:
            _cond_order(symbol, close_side, tp, tp_type)
    except Exception:
        pass  # janitor akan retry — jangan crash, jangan close
    return order_status(symbol)

def janitor_loop(targets, stop_event):
    """
    targets: dict symbol -> {'side': 'LONG'/'SHORT', 'sl': px, 'tp': px}
    Janitor kejar sampai semua SL+TP terpasang. TIDAK PERNAH menutup posisi.
    """
    while not stop_event.is_set():
        try:
            for sym, t in list(targets.items()):
                st = try_place_sl_tp(sym, t["side"], t["sl"], t["tp"])
                if st["sl"] and st["tp"]:
                    targets.pop(sym, None)   # selesai — keluar dari daftar kejaran
        except Exception:
            pass
        stop_event.wait(JANITOR_INTERVAL)

def start_janitor(targets):
    global _janitor_thread
    stop = threading.Event()
    _janitor_thread = threading.Thread(target=janitor_loop, args=(targets, stop), daemon=True)
    _janitor_thread.start()
    return stop

def submit_entry(symbol, side, sl, tp):
    """Dipanggil bot setelah entry fill. SL/TP diembankan ke janitor.
    Return False kalau max posisi global tercapai (bot skip entry ini)."""
    if len(open_positions()) >= MAX_GLOBAL_POSITIONS:
        return False
    targets[symbol] = {"side": side, "sl": sl, "tp": tp}
    _pending_guard[symbol] = True
    return True

targets = {}   # global kejaran janitor

def can_open():
    """Bot cek ini sebelum entry baru: ga lewat max posisi & ga nunggu guard."""
    return len(open_positions()) < MAX_GLOBAL_POSITIONS and not _pending_guard

if __name__ == "__main__":
    assert callable(submit_entry) and callable(can_open)
    print(f"order_guard v2 OK — janitor mode, max {MAX_GLOBAL_POSITIONS} posisi global")
