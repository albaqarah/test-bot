#!/usr/bin/env python3
"""
hybrid_rules.py - Mode HYBRID: fade ekstrem + trend-following pullback.
Dua mesin sinyal jalan bareng:
1. FADE (lama): RSI ekstrem + z ekstrem + wick 0.15 + vol climax  -> lawan arah
2. TREND (baru): HTF bias (EMA20 15m+1h searah) + pullback + rejection candle + vol > 0.8x
   - TREND_UP: LONG saat pullback berakhir (candle reversal naik deket EMA20 15m)
   - TREND_DOWN: SHORT saat rally berakhir (candle reversal turun deket EMA20 15m)
Grade: A = kedua mesin sepakat / konfluensi penuh; B = 1 mesin doang
Semua tetap lolos bos LLM sebelum entry.
"""
import reversion_bot as rb

def ema_series(vals,n):
    k=2/(n+1); out=[vals[0]]
    for v in vals[1:]: out.append(v*k+out[-1]*(1-k))
    return out

def gen_trend_signals(kk, rs, htf15, htf60, vsma):
    """Sinyal trend-following pullback. htf15/htf60 = list EMA20 aligned ke index 5m."""
    sigs=[]
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]; v=[r[5] for r in kk]
    for i in range(60,len(c)-2):
        e15=htf15[i] if i<len(htf15) else None
        e60=htf60[i] if i<len(htf60) else None
        if e15 is None or e60 is None: continue
        rng=h[i]-l[i]
        if rng<=0: continue
        body=abs(c[i]-o[i])
        volx=v[i]/vsma[i] if vsma[i] else 1
        # TREND UP + LONG pullback
        if c[i]>e60 and e15>e60:
            # pullback: harga nyentuh deket EMA20 15m lalu reversal
            near_ema = l[i] <= e15*1.001 and c[i] > o[i]          # sentuh EMA, close hijau
            rsi_ok = 35 <= rs[i] <= 60                             # bukan overbought
            wick = (min(o[i],c[i])-l[i])/rng
            if near_ema and rsi_ok and wick>=0.40 and volx>1.0:
                grade = 'A' if volx>2.0 and wick>=0.55 else 'B'
                sigs.append((i,'L',grade))
        # TREND DOWN + SHORT rally
        elif c[i]<e60 and e15<e60:
            near_ema = h[i] >= e15*0.999 and c[i] < o[i]
            rsi_ok = 40 <= rs[i] <= 65
            wick = (h[i]-max(o[i],c[i]))/rng
            if near_ema and rsi_ok and wick>=0.40 and volx>1.0:
                grade = 'A' if volx>2.0 and wick>=0.55 else 'B'
                sigs.append((i,'S',grade))
    return sigs

def gen_hybrid(kk, rs, zz, vsma, htf15, htf60):
    """Gabung fade + trend, dedupe per bar."""
    fade=rb.gen_signals(kk,rs,zz,vsma)
    trend=gen_trend_signals(kk,rs,htf15,htf60,vsma)
    by_bar={}
    for s in fade: by_bar.setdefault(s[0],[]).append(s)
    for s in trend: by_bar.setdefault(s[0],[]).append(s)
    out=[]
    for i,ss in sorted(by_bar.items()):
        # kalau fade & trend bentrok arah di bar sama -> skip (kabut)
        sides={s[1] for s in ss}
        if len(sides)>1: continue
        # grade naik kalau konfluensi (fade+trend sepakat arah)
        if len(ss)>1:
            out.append((i, ss[0][1], 'A'))
        else:
            out.append(ss[0])
    return out

def build_htf_maps(sym, k5_len):
    """EMA20 dari 15m & 1h, dipetakan ke timeline 5m (backtest)."""
    import importlib.util
    spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
    vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
    maps={}
    for tf,cnt in (('15m',1000),('1h',500)):
        try:
            kh=vg.fetch_hist_klines(sym,tf,cnt)
            c=[float(x[4]) for x in kh]
            e=ema_series(c,20)
            maps[tf]={int(x[0]):e[j] for j,x in enumerate(kh)}
        except Exception:
            maps[tf]={}
    return maps
