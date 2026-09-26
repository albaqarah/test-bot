#!/usr/bin/env python3
"""Backtest V15 Pro Genius signal engine (StochRSI cross + ATR TP/SL + breakeven)
pada data Binance USDⓈ-M 5m publik. Anti-lookahead: sinyal dihitung pada close
candle i, entry di open candle i+1; TP/SL dicek intrabar (konservatif: SL dulu).
Fee taker 0.05%/sisi dihitung atas notional (margin x leverage).
"""
import json, math, os, sys, time, urllib.request

BASE = "https://fapi.binance.com/fapi/v1/klines"
FEE = 0.0005          # taker per sisi
LEVERAGE = 20
MARGIN_PCT = 0.10     # 10% ekuitas per trade
TP_PCT = 0.005
SL_ATR_MULT = 0.8
MIN_SL_PCT = 0.004
BE_TRIGGER = 0.0025
BE_OFFSET = 0.0015
MAX_AGE_BARS = 12     # 1 jam
TP_ATR_MULT = 1.5     # TP juga ATR-based biar R:R >= 1.5
MIN_TP_PCT = 0.004    # TP minimum 0.4% biar gak lebih tipis dari fee
MIN_BE_OFFSET = 0.003 # BE offset di atas fee roundtrip (levered)

def fetch_klines(symbol, interval="5m", total=6000):
    out, end = [], None
    while len(out) < total:
        url = f"{BASE}?symbol={symbol}&interval={interval}&limit=1500"
        if end: url += f"&endTime={end}"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        if not data: break
        out = data + out
        end = data[0][0] - 1
        if len(data) < 1500: break
        time.sleep(0.15)
    return out[-total:]

def stoch_rsi(closes, period=7, k_s=3, d_s=3):
    n = len(closes)
    delta = [closes[i]-closes[i-1] for i in range(1, n)]
    gains, losses = [0.0], []
    for d in delta:
        gains.append(max(d, 0.0)); losses.append(max(-d, 0.0))
    def rma(vals, p):
        out = [None]*(len(vals))
        for i in range(p, len(vals)+1):
            w = vals[i-p:i]
            out[i-1] = sum(w)/p
        return out
    ga, lo = rma(gains, period), rma(losses, period)
    rsi = [100 - 100/(1+(ga[i]/(lo[i]+1e-9))) if ga[i] is not None and lo[i] is not None else None for i in range(len(ga))]
    valid = [r for r in rsi if r is not None]
    if len(valid) < period: return None, None
    # stoch of rsi over last `period` valid values (approx of rolling)
    win = valid[-period:]
    st = (win[-1] - min(win)) / (max(win) - min(win) + 1e-9) * 100
    return st, st  # K/D cross handled via history below

def atr_series(h, l, c, period=14):
    trs = []
    for i in range(1, len(c)):
        tr = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        trs.append(tr)
    out = [None]*(len(c)-len(trs))
    sm = sum(trs[:period])/period
    out.append(sm)
    for i in range(period, len(trs)):
        sm = (sm*(period-1)+trs[i])/period
        out.append(sm)
    return [None]*(period+1) + out

def backtest(symbol, bars=6000):
    k = fetch_klines(symbol, "5m", bars)
    t = [int(x[0]) for x in k]; o=[float(x[1]) for x in k]; h=[float(x[2]) for x in k]
    l=[float(x[3]) for x in k]; c=[float(x[4]) for x in k]
    atrs = atr_series(h, l, c)
    closes = c
    equity = 100.0; peak = equity; maxdd = 0.0
    trades = []; pos = None
    stoch_hist = []
    # precompute stoch K series for cross detection
    kvals = [None]*(len(c))
    for i in range(60, len(c)):
        win = closes[i-7:i+1]
        d_ = [win[j]-win[j-1] for j in range(1, len(win))]
        g = sum(max(x,0) for x in d_)/7; lo_ = sum(max(-x,0) for x in d_)/7
        rsi = 100 - 100/(1+(g/(lo_+1e-9)))
        rwin = []
        # approximate stoch-rsi using rsi of last 7 windows -> use rsi series
        kvals[i] = rsi  # store rsi; stoch over rsi window computed below
    # proper stoch-rsi K
    rsi_v = [None]*len(c)
    for i in range(15, len(c)):
        win = closes[i-14:i+1]
        d_ = [win[j]-win[j-1] for j in range(1, len(win))]
        g = sum(max(x,0) for x in d_)/14; lo_ = sum(max(-x,0) for x in d_)/14
        rsi_v[i] = 100 - 100/(1+(g/(lo_+1e-9)))
    stochK = [None]*len(c)
    for i in range(21, len(c)):
        rw = [x for x in rsi_v[i-6:i+1] if x is not None]
        if len(rw) < 5: continue
        stochK[i] = (rw[-1]-min(rw))/(max(rw)-min(rw)+1e-9)*100
    def smooth(vals, p):
        out=[None]*len(vals)
        for i in range(p, len(vals)):
            w=[x for x in vals[i-p+1:i+1] if x is not None]
            if len(w)==p: out[i]=sum(w)/p
        return out
    stochD = smooth(stochK, 3)

    i = 30
    while i < len(c)-1:
        # manage open position first (entry at open of bar i)
        if pos is not None:
            e = pos["entry"]; amt = pos["amt"]; side = pos["side"]
            hit_tp = (h[i] >= pos["tp"]) if side=="LONG" else (l[i] <= pos["tp"])
            hit_sl = (l[i] <= pos["sl"]) if side=="LONG" else (h[i] >= pos["sl"])
            exit_px = None
            if hit_sl and hit_tp: exit_px = pos["sl"]      # konservatif
            elif hit_sl: exit_px = pos["sl"]
            elif hit_tp:
                # breakeven check before TP exit
                exit_px = pos["tp"]
            if exit_px is None and pos["age"] >= MAX_AGE_BARS:
                exit_px = c[i]  # time exit
            if exit_px is not None:
                move = (exit_px-e)/e * (1 if side=="LONG" else -1)
                # breakeven offset already embedded if sl moved
                pnl_pct = move * LEVERAGE - 2*FEE*LEVERAGE   # leveraged move, fee atas notional
                pnl = equity * MARGIN_PCT * LEVERAGE * pnl_pct
                equity += pnl
                trades.append({"t": t[i], "side": side, "pnl_pct": pnl_pct*100,
                               "pnl_usd": pnl, "equity": equity})
                pos = None
            else:
                pos["age"] += 1
                # breakeven move
                move = (c[i]-e)/e * (1 if side=="LONG" else -1)
                if move >= BE_TRIGGER and not pos["be"]:
                    pos["be"] = True
                    off = max(BE_OFFSET, MIN_BE_OFFSET)
                    if side=="LONG": pos["sl"] = e*(1+off)
                    else: pos["sl"] = e*(1-off)
                i += 1; continue
        if pos is None and i+1 < len(c):
            a = atrs[i]
            K, D = stochK[i], stochD[i]
            Kp, Dp = stochK[i-1], stochD[i-1]
            if a and K and D and Kp and Dp and a > 0:
                cross_up = Kp <= Dp and K > D
                cross_dn = Kp >= Dp and K < D
                if cross_up and K < 30:
                    entry = o[i+1]
                    sl_d = max(SL_ATR_MULT*a, entry*MIN_SL_PCT)
                    tp_d = max(TP_ATR_MULT*a, entry*MIN_TP_PCT)
                    pos = {"side":"LONG","entry":entry,"amt":1,"tp":entry+tp_d,
                           "sl":entry-sl_d,"age":0,"be":False}
                elif cross_dn and K > 70:
                    entry = o[i+1]
                    sl_d = max(SL_ATR_MULT*a, entry*MIN_SL_PCT)
                    tp_d = max(TP_ATR_MULT*a, entry*MIN_TP_PCT)
                    pos = {"side":"SHORT","entry":entry,"amt":1,"tp":entry-tp_d,
                           "sl":entry+sl_d,"age":0,"be":False}
        peak = max(peak, equity); maxdd = max(maxdd, (peak-equity)/peak)
        i += 1

    wins = [t for t in trades if t["pnl_usd"]>0]; losses=[t for t in trades if t["pnl_usd"]<=0]
    r = {"symbol": symbol, "trades": len(trades),
         "winrate": round(100*len(wins)/len(trades),1) if trades else 0,
         "equity_end": round(equity,2), "return_pct": round(equity-100,2),
         "max_dd_pct": round(maxdd*100,2),
         "avg_win": round(sum(t["pnl_usd"] for t in wins)/len(wins),3) if wins else 0,
         "avg_loss": round(sum(t["pnl_usd"] for t in losses)/len(losses),3) if losses else 0}
    return r, trades

if __name__ == "__main__":
    symbols = sys.argv[1:] or ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","XRPUSDT"]
    all_r = []
    for s in symbols:
        r, trades = backtest(s)
        all_r.append(r)
        print(json.dumps(r))
    # portfolio: sequential per-symbol equity compounding is approximated independently
    tot = sum(r["return_pct"] for r in all_r)
    print(f"\nTOTAL (sum of per-symbol returns on $100 each): {tot:+.2f}%")
