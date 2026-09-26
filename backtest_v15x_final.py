#!/usr/bin/env python3
"""V15-X final — JEV concept → Binance perp.
Sinyal (maker filosofi): entry kontra-ekstrem, saat pressure menipis:
  LONG : imbalance <= -imb_th (selling climax) + candle reversal (close>open)
  SHORT: imbalance >= +imb_th (buying climax) + candle reversal (close<open)
Plus CVD filter (taker flow searah entry) kalau datanya ada.
Maker entry (fee 0.02%), SL taker (fee 0.05%).
IS = 6000 bar terbaru, OOS = 6000 bar sebelum IS (15-36 hari lalu).
"""
import json, time, urllib.request, sys
import os

FEE_MAKER=0.0002; FEE_TAKER=0.0005; LEV=3; MARGIN=0.10

def get(u):
    with urllib.request.urlopen(u, timeout=30) as r: return json.loads(r.read())

def fetch_hist_klines(sym, interval="5m", total=6000, end=None):
    out=[]
    while len(out)<total:
        u=f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&limit=1500&endTime={end}" if end else \
          f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&limit=1500"
        d=get(u)
        if not d: break
        out=d+out; end=d[0][0]-1
        if len(d)<1500: break
        time.sleep(0.12)
    return out[-total:]

def fetch_cvd(sym, period="5m", limit=500):
    try:
        d=get(f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={sym}&period={period}&limit={limit}")
        return {int(x["timestamp"])//1000:float(x["buySellRatio"]) for x in d}
    except Exception: return {}

def imbalance(k):
    imb=[]
    for x in k:
        o,h,l,c=float(x[1]),float(x[2]),float(x[3]),float(x[4])
        rng=h-l
        if rng<=0: imb.append(0.0); continue
        upper=h-max(o,c); lower=min(o,c)-l
        imb.append((lower-upper)/rng)
    return imb

def run(k, cvd_map, imb_th=0.35, use_cvd=True, cvd_th=0.05):
    t=[int(x[0]) for x in k]; o=[float(x[1]) for x in k]; h=[float(x[2]) for x in k]
    l=[float(x[3]) for x in k]; c=[float(x[4]) for x in k]
    imb=imbalance(k)
    equity=100.0; peak=100.0; maxdd=0.0; trades=[]; pos=None; n_sig=0
    for i in range(30,len(c)-1):
        if pos:
            e=pos["entry"]
            hit_sl = l[i]<=pos["sl"] if pos["side"]=="L" else h[i]>=pos["sl"]
            hit_tp = h[i]>=pos["tp"] if pos["side"]=="L" else l[i]<=pos["tp"]
            px = pos["sl"] if hit_sl else (pos["tp"] if hit_tp else None)
            if px is None and pos["age"]>=48: px=c[i]
            if px is not None:
                mv=(px-e)/e*(1 if pos["side"]=="L" else -1)
                fee_exit = FEE_TAKER if hit_sl else FEE_MAKER
                pnl=equity*MARGIN*(mv*LEV-(FEE_MAKER+fee_exit)*LEV)
                equity+=pnl; trades.append(pnl); pos=None
            else:
                pos["age"]+=1
                mv=(c[i]-e)/e*(1 if pos["side"]=="L" else -1)
                if mv>=0.003 and not pos["be"]:
                    pos["be"]=True
                    pos["sl"]=e*(1+0.0004) if pos["side"]=="L" else e*(1-0.0004)
                peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
                continue
        if pos is None:
            im=imb[i]
            bull = c[i]>o[i]; bear = c[i]<o[i]
            cvd=cvd_map.get(t[i]//1000)
            # contrarian: selling climax menipis → LONG
            if im<=-imb_th and bull and (not use_cvd or cvd is None or cvd<1+cvd_th):
                n_sig+=1
                entry=o[i+1]; sl_d=max(0.004,entry*0.004); tp_d=sl_d*2
                pos={"side":"L","entry":entry,"sl":entry-sl_d,"tp":entry+tp_d,"age":0,"be":False}
            elif im>=imb_th and bear and (not use_cvd or cvd is None or cvd>1-cvd_th):
                n_sig+=1
                entry=o[i+1]; sl_d=max(0.004,entry*0.004); tp_d=sl_d*2
                pos={"side":"S","entry":entry,"sl":entry+sl_d,"tp":entry-tp_d,"age":0,"be":False}
        peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
    wr=100*sum(1 for p in trades if p>0)/len(trades) if trades else 0
    return {"signals":n_sig,"trades":len(trades),"wr":round(wr,1),
            "ret":round(equity-100,1),"maxdd":round(maxdd*100,1)}

if __name__=="__main__":
    syms=sys.argv[1:] or ["BTCUSDT","ETHUSDT","SOLUSDT"]
    all_results={}
    for s in syms:
        try:
            cvd=fetch_cvd(s)
            # IS: 6000 bar terbaru
            is_k=fetch_hist_klines(s,"5m",6000)
            is_end=is_k[0][0]-1
            is_r=run(is_k,cvd)
            # OOS: 6000 bar sebelum IS
            oos_k=fetch_hist_klines(s,"5m",6000,end=is_end)
            oos_r=run(oos_k,cvd)
            all_results[s]={"IS":is_r,"OOS":oos_r}
            print(json.dumps({"symbol":s,"IS":is_r,"OOS":oos_r}))
        except Exception as e:
            print(json.dumps({"symbol":s,"error":str(e)[:80]}))
        time.sleep(0.3)
    json.dump(all_results, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15x_results.json'),'w'), indent=1)
