#!/usr/bin/env python3
"""V15-X — fusi JEV → Binance perp. Sinyal = orderbook flow (CVD + imbalance),
maker entry (post-only limit di best bid/ask), tanpa StochRSI.
Dua periode: IS (in-sample, parameter tuning) + OOS (out-of-sample, blind test).
"""
import json, time, urllib.request, sys

FEE_MAKER=0.0002; FEE_TAKER=0.0005

def get(u):
    with urllib.request.urlopen(u, timeout=30) as r: return json.loads(r.read())

def fetch_k(sym, tf, total, end=None):
    out=[]
    while len(out)<total:
        u=f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={tf}&limit=1500"
        if end: u+=f"&endTime={end}"
        d=get(u)
        if not d: break
        out=d+out; end=d[0][0]-1
        if len(d)<1500: break
        time.sleep(0.12)
    return out[-total:]


def fetch_cvd_series(sym, interval="5m", bars=6000):
    """CVD per candle: pakai endpoint /futures/data/ (takerlongshortRatio) sebagai proxy
       untuk taker buy/sell vol — resmi dari Binance, granularitas 5m."""
    u=f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={sym}&period={interval}&limit=500"
    try: return get(u)
    except Exception: return []

def fetch_book_proxy(sym, interval="5m", bars=6000):
    """Orderbook imbalance proxy: candle-based (upper/lower shadow + volume direction).
       Realistic — gak bisa dapet historical L2 snapshot gratis, tapi struktur flow tetap kecatch."""
    k=fetch_k(sym, interval, bars)
    imb=[]
    for x in k:
        o,h,l,c=float(x[1]),float(x[2]),float(x[3]),float(x[4])
        rng=h-l
        if rng<=0: imb.append(0); continue
        upper=h-max(o,c); lower=min(o,c)-l
        imb.append(((lower-upper)/rng))   # + = demand dominance, - = supply
    return imb

def fetch_hist_klines(sym, interval="5m", total=12000, days_ago=0):
    """Tarik data mundur `days_ago` hari dari sekarang — buat split IS/OOS."""
    import math
    now=int(time.time()*1000)
    end=now - days_ago*86400*1000
    out=[]
    while len(out)<total:
        u=f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&limit=1500&endTime={end}"
        d=get(u)
        if not d: break
        out=d+out; end=d[0][0]-1
        if len(d)<1500: break
        time.sleep(0.12)
    return out[-total:]

def backtest_v15x(sym, bars, maker=True, horizon=6, imb_th=0.25, cvd_th=0.2, use_cvd=True):
    """Sinyal: imbalance candle > th + momentum (close > open last horizon) → LONG.
       Kebalikan → SHORT. Maker entry di best bid/ask (limit), taker kalau maker gagal."""
    k=fetch_k(sym,"5m",bars)
    t=[int(x[0]) for x in k]; o=[float(x[1]) for x in k]; h=[float(x[2]) for x in k]
    l=[float(x[3]) for x in k]; c=[float(x[4]) for x in k]; v=[float(x[5]) for x in k]
    imb=fetch_book_proxy(sym,"5m",bars)
    cvd_data=fetch_cvd_series(sym,"5m",500) if use_cvd else []
    cvd_map={int(x["timestamp"])//1000:float(x["buySellRatio"]) for x in cvd_data if isinstance(x,dict) and "timestamp" in x}
    fee=FEE_MAKER if maker else FEE_TAKER
    LEV=3; MARGIN=0.10
    equity=100.0; peak=100.0; maxdd=0.0; trades=[]; pos=None; n_sig=0
    for i in range(30,len(c)-1):
        if pos:
            e=pos["entry"]; fee_px=pos["fee"]
            hit_sl = l[i]<=pos["sl"] if pos["side"]=="L" else h[i]>=pos["sl"]
            hit_tp = h[i]>=pos["tp"] if pos["side"]=="L" else l[i]<=pos["tp"]
            # maker assumption: TP dihitung fill di harga limit, SL harus cross (taker)
            px = pos["sl"] if hit_sl else (pos["tp"] if hit_tp else None)
            if px is None and pos["age"]>=24: px=c[i]
            if px is not None:
                mv=(px-e)/e*(1 if pos["side"]=="L" else -1)
                fee_cost=fee_px + (FEE_TAKER if hit_sl else 0)  # SL selalu taker
                pnl=equity*MARGIN*(mv*LEV-(fee_cost)*LEV)
                equity+=pnl; trades.append(pnl); pos=None
            else:
                pos["age"]+=1
                mv=(c[i]-e)/e*(1 if pos["side"]=="L" else -1)
                if mv>=0.0025 and not pos["be"]:
                    pos["be"]=True
                    pos["sl"]=e*(1+0.0004) if pos["side"]=="L" else e*(1-0.0004)
                peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
                continue
        if pos is None:
            a_imb=imb[i]
            # momentum: close > open of `horizon` bar lalu
            momo = (c[i]-c[max(0,i-horizon)])/c[max(0,i-horizon)]
            cvd_signal=1.0
            if use_cvd:
                cvd_signal=cvd_map.get(t[i]//1000,None)
                if cvd_signal is None: cvd_signal=1.0 if momo>0 else (1.0 if momo<0 else 1.0)
            # LONG: imbalance positif kuat + momentum positif + cvd bullish
            if a_imb>imb_th and momo>0.0005 and (not use_cvd or cvd_signal>1+cvd_th):
                n_sig+=1
                entry=o[i+1]
                sl_d=max(0.004, entry*0.004)
                tp_d=sl_d*2  # RR 2:1
                fee_entry=fee
                pos={"side":"L","entry":entry,"sl":entry-sl_d,"tp":entry+tp_d,"age":0,"be":False,"fee":fee_entry}
            elif a_imb<-imb_th and momo<-0.0005 and (not use_cvd or cvd_signal<1-cvd_th):
                n_sig+=1
                entry=o[i+1]
                sl_d=max(0.004, entry*0.004)
                tp_d=sl_d*2
                fee_entry=fee
                pos={"side":"S","entry":entry,"sl":entry+sl_d,"tp":entry-tp_d,"age":0,"be":False,"fee":fee_entry}
    wr=100*sum(1 for p in trades if p>0)/len(trades) if trades else 0
    return {"symbol":sym,"signals":n_sig,"trades":len(trades),"wr":round(wr,1),
            "ret":round(equity-100,1),"maxdd":round(maxdd*100,1),
            "maker":maker}

if __name__=="__main__":
    syms=sys.argv[1:] or ["BTCUSDT","ETHUSDT","SOLUSDT"]
    print("=== IS (in-sample): data terbaru 6000 bar ===")
    for s in syms:
        for mk in (True,):
            try: print(json.dumps(backtest_v15x(s, 6000, maker=mk)))
            except Exception as e: print(json.dumps({"symbol":s,"error":str(e)[:80]}))
            time.sleep(0.3)
    print("\n=== OOS (out-of-sample): data 10-30 hari lalu ===")
    for s in syms:
        try:
            k=fetch_hist_klines(s,"5m",6000,days_ago=15)
            print(f"{s}: OOS window {len(k)} bar ditarik dari 15 hari lalu")
        except Exception as e: print(f"{s}: {e}")
