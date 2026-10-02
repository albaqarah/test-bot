#!/usr/bin/env python3
"""
gmv2.py — GODMODE V2 ENGINE (port stdlib dari repo v15-pro-genius/godmode_v2_engine.py)
Diterapkan ke kurir & bos (directive user 2 Okt, tanpa backtest): FeatureEngine +
GodModeScorer jadi SENSOR KUANTITATIF: kurir hitung skor GM utk arah sinyal, bos jev
pakai skor+tier sbg kompas di payload.godmode. Bot TETAP bosnya jev (GMV2 bukan pengganti).

Deviasi terdokumentasi (kompromi runtime tanpa numpy/pandas + mandat user):
1. RSI: GMV2 asli pakai RSI(5) SMA-rolling utk 5m — port pakai RSI(6) SMA-rolling
   (window sama dgn mandate RSI6 user; algoritma rolling-mean GMV2 asli dipertahankan,
   Wilder rsi6 reversion_bot tetap taxak di pipeline sinyal).
2. 15m: RSI(6) & stoch_rsi dari closes 15m stash build_htf_maps (GMV2 asli RSI14 15m).
3. Struktur swing: pakai bar 5m array (logika fractal 2/2 + near_support/resistance verbatim).
"""
import math
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

FEATURE_WEIGHTS = {
    "trend": 25, "momentum": 20, "mtf_alignment": 15,
    "liquidity": 15, "volume": 10, "volatility": 10, "session": 5,
}
MEAN_REVERSION_WEIGHTS = {
    "trend": 5, "momentum": 30, "mtf_alignment": 5,
    "liquidity": 30, "volume": 10, "volatility": 10, "session": 10,
}
TIER_THRESHOLDS = {"sniper": 90, "execute": 75, "watch": 71, "reject": 0}

def _clip(x, lo=0.0, hi=100.0): return max(lo, min(hi, x))

def _ema_series(c, span):
    """EMA standar (adjust=False setara pandas ewm span)."""
    a = 2.0/(span+1.0); out=[c[0]]
    for x in c[1:]: out.append(out[-1]+a*(x-out[-1]))
    return out

def rsi_sma(c, n=6):
    """RSI window-n ala GMV2 (SMA rolling, bukan Wilder) — dipakai khusus sensor GM."""
    if len(c) < n+1: return [50.0]*len(c)
    g=[0.0]*len(c); lo=[0.0]*len(c)
    for i in range(1,len(c)):
        d=c[i]-c[i-1]; g[i]=max(d,0.0); lo[i]=max(-d,0.0)
    out=[None]*len(c)
    for i in range(n,len(c)):
        ag=sum(g[i-n+1:i+1])/n; al=sum(lo[i-n+1:i+1])/n or 1e-9
        out[i]=100.0-100.0/(1.0+ag/al)
    return out

def stoch_rsi(c, p=7, sk=3, sd=3):
    r=rsi_sma(c,p)
    rv=[x if x is not None else 50.0 for x in r]
    k=[50.0]*len(c)
    for i in range(p,len(c)):
        w=rv[i-p+1:i+1]; mn=min(w); mx=max(w)
        k[i]=(rv[i]-mn)/(mx-mn+1e-9)*100
    sm=[50.0]*len(c)
    for i in range(p+sk-1,len(c)): sm[i]=sum(k[i-sk+1:i+1])/sk
    d=[50.0]*len(c)
    for i in range(p+sk+sd-2,len(c)): d[i]=sum(sm[i-sd+1:i+1])/sd
    return k[-1], d[-1]

def compute_features(kk5, c15, rsi6_5m=None):
    """kk5: bar 5m [ts,o,h,l,c,v]; c15: closes 15m (stash build_htf_maps); rsi6_5m: seri rsi6 Wilder (mandat)."""
    o=[r[1] for r in kk5]; h=[r[2] for r in kk5]; l=[r[3] for r in kk5]
    c=[r[4] for r in kk5]; v=[r[5] for r in kk5]
    if len(c)<50: return None
    rsi6s = rsi6_5m if (rsi6_5m and len(rsi6_5m)==len(c) and rsi6_5m[-1] is not None) else rsi_sma(c,6)
    rsi = float(rsi6s[-1]); rsi_prev = float(rsi6s[-3]) if len(rsi6s)>3 and rsi6s[-3] is not None else rsi
    sk, sd = stoch_rsi(c,7,3,3)
    # trend: EMA20/50 + slope (GMV2 verbatim)
    e20=_ema_series(c,20); e50=_ema_series(c,50); p=c[-1]
    if p>e20[-1]>e50[-1]: al=80.0
    elif p<e20[-1]<e50[-1]: al=20.0
    else: al=50.0
    slope=(e20[-1]-e20[-5])/e20[-1]*10000 if e20[-1] else 0.0
    slope_s=50+_clip(slope*5,-50,50)
    trend_score=_clip(al*0.6+slope_s*0.4)
    # momentum extra: macd_hist
    e12=_ema_series(c,12); e26=_ema_series(c,26)
    macd=[a-b for a,b in zip(e12,e26)]; macd_sig=_ema_series(macd,9)
    macd_hist=macd[-1]-macd_sig[-1]
    # volatility: ATR14 sma + percentile + BB width (GMV2 verbatim)
    tr=[]
    for i in range(1,len(c)):
        tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    atr_s=[sum(tr[max(0,i-13):i+1])/len(tr[max(0,i-13):i+1]) for i in range(len(tr))]
    atr=atr_s[-1] if atr_s else 0.0
    atr_pct=atr/p*100 if p>0 else 0.0
    atr_pctl=(sum(1 for x in atr_s if atr_s[-1]>x)/len(atr_s)*100) if atr_s else 50.0
    sma20=sum(c[-20:])/20
    std=math.sqrt(sum((x-sma20)**2 for x in c[-20:])/20) or 1e-9
    bbw=( (sma20+2*std)-(sma20-2*std) )/sma20*100
    # volume
    vma=sum(v[-20:])/20 or 1e-9
    vr=v[-1]/vma
    # structure: fractal swing 2/2 + near_support/resistance (GMV2 verbatim, 20000 factor)
    sh=[]; sl=[]
    for i in range(2,len(h)-2):
        if h[i]>h[i-1] and h[i]>h[i-2] and h[i]>h[i+1] and h[i]>h[i+2]: sh.append(h[i])
        if l[i]<l[i-1] and l[i]<l[i-2] and l[i]<l[i+1] and l[i]<l[i+2]: sl.append(l[i])
    ns=max(0.0, 100-min((abs(p-s)/p*20000 for s in sl[-3:]), default=0.0)) if sl else 0.0
    nr=max(0.0, 100-min((abs(p-r)/p*20000 for r in sh[-3:]), default=0.0)) if sh else 0.0
    sc=50.0
    if len(sh)>=2 and len(sl)>=2:
        if sh[-1]>sh[-2] and sl[-1]>sl[-2]: sc=75.0
        elif sh[-1]<sh[-2] and sl[-1]<sl[-2]: sc=25.0
    # MTF: 5m rsi6 vs 15m (rsi6 15m + stoch_k_15m) + posisi vs ema20 masing TF
    r15 = rsi_sma(c15,6)[-1] if c15 and len(c15)>=8 else 50.0
    sk15,_ = stoch_rsi(c15,7,3,3) if c15 and len(c15)>=20 else (50.0,50.0)
    e20_15=_ema_series(c15,20)[-1] if c15 and len(c15)>=20 else p
    a5 = p>e20[-1]; a15 = p>e20_15
    ms = 80.0 if (a5 and a15) else (20.0 if (not a5 and not a15) else 50.0)
    # session WIB (GMV2 verbatim)
    hh=datetime.now(WIB).hour
    if 15<=hh<21: sess,ss="LONDON",90
    elif 21<=hh or hh<3: sess,ss="NEW_YORK",85
    elif 3<=hh<7: sess,ss="OVERLAP",95
    else: sess,ss="ASIA",70
    return {"trend_score":round(trend_score,1),"ema_slope":round(slope_s,1),
            "rsi5":round(rsi,1),"rsi_slope":round(rsi-rsi_prev,2),
            "stoch_k":round(sk,1),"stoch_d":round(sd,1),"macd_hist":round(macd_hist,6),
            "momentum_score":round(rsi,1),
            "atr":round(atr,6),"atr_pct":round(atr_pct,4),"atr_percentile":round(atr_pctl,1),
            "bb_width":round(bbw,2),"volatility_score":round(_clip(atr_pctl),1),
            "volume_ratio":round(vr,2),"volume_spike":vr>1.5,
            "volume_score":round(_clip(vr*40),1),
            "mtf_alignment_score":round(ms,1),"rsi_15m":round(float(r15),1),"stoch_k_15m":round(sk15,1),
            "structure_score":round(sc,1),"near_support":round(ns,1),"near_resistance":round(nr,1),
            "session":sess,"session_score":ss,"_price":p}

def detect_setup_type(f, direction):
    rsi=f.get("rsi5",50.0); sk=f.get("stoch_k",50.0); sk15=f.get("stoch_k_15m",50.0)
    ns=f.get("near_support",0.0); nr=f.get("near_resistance",0.0)
    if direction=="LONG":
        if sk<15 and ns>30: return "MEAN_REVERSION"
        if rsi<20 and ns>30: return "MEAN_REVERSION"
        if rsi<35 and sk<35 and ns>50: return "MEAN_REVERSION"
        if sk<20 and sk15<30 and ns>20: return "MEAN_REVERSION"
    else:
        if sk>85 and nr>30: return "MEAN_REVERSION"
        if rsi>80 and nr>30: return "MEAN_REVERSION"
        if rsi>65 and sk>65 and nr>50: return "MEAN_REVERSION"
        if sk>80 and sk15>70 and nr>20: return "MEAN_REVERSION"
    return "TREND_CONTINUATION"

def score(f, direction):
    setup=detect_setup_type(f,direction)
    w=dict(MEAN_REVERSION_WEIGHTS) if setup=="MEAN_REVERSION" else dict(FEATURE_WEIGHTS)
    bd={"setup_type":setup}
    raw_trend=f.get("trend_score",50.0)
    bd["trend"]=50.0 if setup=="MEAN_REVERSION" else (raw_trend if direction=="LONG" else 100.0-raw_trend)
    rsi=f.get("rsi5",50.0); slope=f.get("rsi_slope",0.0); sk_val=f.get("stoch_k",50.0)
    if setup=="MEAN_REVERSION":
        if direction=="LONG":
            extreme=max(100.0-rsi, 100.0-sk_val)
            mom=extreme*0.7+max(0.0,slope*10+50.0)*0.3
        else:
            extreme=max(rsi, sk_val)
            mom=extreme*0.7+max(0.0,-slope*10+50.0)*0.3
    else:
        if direction=="LONG": mom=(100.0-rsi)*0.6+max(0.0,slope*10+50.0)*0.4
        else: mom=rsi*0.6+max(0.0,-slope*10+50.0)*0.4
    bd["momentum"]=_clip(mom)
    mtf=f.get("mtf_alignment_score",50.0)
    bd["mtf_alignment"]=50.0 if setup=="MEAN_REVERSION" else (mtf if direction=="LONG" else 100.0-mtf)
    ns=f.get("near_support",0.0); nr=f.get("near_resistance",0.0)
    raw_liq=_clip(ns if direction=="LONG" else nr)
    bd["liquidity"]=_clip(raw_liq*1.1) if setup=="MEAN_REVERSION" else raw_liq
    bd["volume"]=min(100.0, f.get("volume_score",50.0)+(15.0 if f.get("volume_spike") else 0.0))
    atr_pct=f.get("atr_pct",0.1)
    if 0.05<atr_pct<0.3: vv=70.0
    elif atr_pct<=0.05: vv=30.0
    else: vv=40.0
    bd["volatility"]=(vv+f.get("volatility_score",50.0))/2
    bd["session"]=f.get("session_score",50.0)
    total=_clip(sum(bd.get(k,50.0)*(wt/100.0) for k,wt in w.items()))
    if setup=="MEAN_REVERSION":
        if direction=="LONG" and rsi<10: total=min(100.0,total+5)
        elif direction=="SHORT" and rsi>90: total=min(100.0,total+5)
    if total>=TIER_THRESHOLDS["sniper"]: tier="SNIPER"
    elif total>=TIER_THRESHOLDS["execute"]: tier="EXECUTE"
    elif total>=TIER_THRESHOLDS["watch"]: tier="WATCH"
    else: tier="REJECT"
    return round(total,1), tier, bd

def best_direction(f):
    sl_,tl,bl=score(f,"LONG"); ss_,ts,bs=score(f,"SHORT")
    if sl_>ss_: return "LONG",sl_,tl,bl
    if ss_>sl_: return "SHORT",ss_,ts,bs
    return "NEUTRAL",sl_,tl,bl

def gm_line(f, direction, sc, tier, setup):
    return (f"GM{sc:.0f}/{tier}({setup[:2]}) · RSI6 {f.get('rsi5')} · StochK {f.get('stoch_k')} · "
            f"t{f.get('trend_score')} m{f.get('mtf_alignment_score')} l{f.get('near_support' if direction=='LONG' else 'near_resistance')} "
            f"v{f.get('volume_ratio')} ATR% {f.get('atr_pct')} · {f.get('session')}")

def evaluate(kk5, c15, direction, rsi6_5m=None):
    """Entri utama kurir: fitur + skor utk ARAH SINYAL. Return dict atau None (data kurang)."""
    f=compute_features(kk5,c15,rsi6_5m)
    if f is None: return None
    sc,tier,bd=score(f,direction)
    return {"score":sc,"tier":tier,"setup":bd.get("setup_type"),"breakdown":bd,
            "direction":direction,"line":gm_line(f,direction,sc,tier,bd.get("setup_type")),
            "rsi6":f.get("rsi5"),"stoch_k":f.get("stoch_k")}

def best_for(kk5, c15, rsi6_5m=None):
    """Skor dua arah + arah terbaik (sensor kuantitatif penuh utk bos)."""
    f=compute_features(kk5,c15,rsi6_5m)
    if f is None: return None
    dl_,sl_,tl_,bl_=best_direction(f)
    sc,tier,bd=score(f,dl_) if dl_!="NEUTRAL" else (sl_,tl_,bl_)
    return {"score":sc,"tier":tier,"setup":bd.get("setup_type"),"best":dl_,
            "breakdown":bd,"line":gm_line(f,dl_ if dl_!="NEUTRAL" else "LONG",sc,tier,bd.get("setup_type")),
            "rsi6":f.get("rsi5"),"stoch_k":f.get("stoch_k")}
