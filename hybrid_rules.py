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
                grade = 'A' if volx>1.5 and wick>=0.55 else 'B'
                sigs.append((i,'L',grade))
        # TREND DOWN + SHORT rally
        elif c[i]<e60 and e15<e60:
            near_ema = h[i] >= e15*0.999 and c[i] < o[i]
            rsi_ok = 40 <= rs[i] <= 65
            wick = (h[i]-max(o[i],c[i]))/rng
            if near_ema and rsi_ok and wick>=0.40 and volx>1.0:
                grade = 'A' if volx>1.5 and wick>=0.55 else 'B'
                sigs.append((i,'S',grade))
    return sigs

def gen_hybrid(kk, rs, zz, vsma, htf15, htf60, extra_engines=None):
    """Gabung fade + trend + (opsional) P6-loose & P5-scalp, dedupe per bar.
    extra_engines: None | 'p6' (fade longgar, toggle .env P6_LOOSE=on)
                   | 'scalp' (kurir momentum) | 'all'
    Output: (idx, side, grade, src) — src utk freshness window di dewa_live."""
    fade=rb.gen_signals(kk,rs,zz,vsma)
    trend=gen_trend_signals(kk,rs,htf15,htf60,vsma)
    allsigs=[(s[0],s[1],s[2],'fade') for s in fade]+[(s[0],s[1],s[2],'trend') for s in trend]
    if extra_engines in ('p6','all'):
        allsigs+=[(s[0],s[1],s[2],'p6') for s in gen_loose_fade(kk,rs,zz,vsma)]
    if extra_engines in ('scalp','all'):
        allsigs+=[(s[0],s[1],s[2],'scalp') for s in gen_scalp(kk,rs,zz,vsma)]
    by_bar={}
    for s in allsigs: by_bar.setdefault(s[0],[]).append(s)
    out=[]
    for i,ss in sorted(by_bar.items()):
        # kalau arah bentrok di bar sama -> skip (kabut)
        sides={s[1] for s in ss}
        if len(sides)>1: continue
        # prioritas grade A; dua engine sepakat -> A; source engine pertama
        grades=[s[2] for s in ss]
        grade='A' if (len(ss)>1 or 'A' in grades) else 'B'
        out.append((i, ss[0][1], grade, ss[0][3]))
    return out

def gen_loose_fade(kk, rs, zz, vsma):
    """P6 — fade longgar, 2 varian dari backtest 30 hari (keduanya expectancy positif):
       A: z>=3.0 bypass imb (RSI ekstrem tetap)  |  B: RSI 70/30 + z>2.5 + imb standar
       Grade B (belum pernah dibuktikan lebih baik dr grade A fade asli)."""
    sigs=[]
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]
    for i in range(210,len(c)-2):
        r=rs[i]; z=zz[i]
        if r is None or z is None: continue
        rng=h[i]-l[i]
        if rng<=0: continue
        imb=((min(o[i],c[i])-l[i])-(h[i]-max(o[i],c[i])))/rng
        if r>75 and z>=3.0 and imb>=-0.5: sigs.append((i,'S','B'))
        elif r<25 and z<=-3.0 and imb<=0.5: sigs.append((i,'L','B'))
        elif r>70 and z>2.5 and imb>=0.15: sigs.append((i,'S','B'))
        elif r<30 and z<-2.5 and imb<=-0.15: sigs.append((i,'L','B'))
    return sigs

def gen_scalp(kk, rs, zz, vsma, obv=None):
    """P5 — kurir momentum scalper (hasil backtest 30 hari: 11.5k trade, avg +$0.117):
       1) stoch_rsi belok dari ekstrem (>80 turun = SHORT / <20 naik = LONG)
       2) breakout: volx>2.5 + body>60% range searah
       Konfirmasi: OBV 10-bar searah trade + volx>=1.2.
       Grade A = volx>=1.5, B = sisanya."""
    sigs=[]
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]; v=[r[5] for r in kk]
    rs2=_stoch_from_rsi(rs)
    if obv is None:
        obv=[0.0]
        for i in range(1,len(c)):
            obv.append(obv[-1]+(v[i] if c[i]>c[i-1] else (-v[i] if c[i]<c[i-1] else 0)))
    for i in range(210,len(c)-2):
        if i<1: continue
        a=rs2[i]; b=rs2[i-1]
        if a is None or b is None: continue
        rng=h[i]-l[i]
        if rng<=0 or vsma[i] is None: continue
        volx=v[i]/vsma[i]
        if volx<1.2: continue
        obv_dir=obv[i]-obv[i-10]
        turn_s = b>80 and a<b-3
        turn_l = b<20 and a>b+3
        body=abs(c[i]-o[i])/rng
        brk_s = volx>2.5 and body>0.6 and c[i]<o[i]
        brk_l = volx>2.5 and body>0.6 and c[i]>o[i]
        if (turn_s or brk_s) and obv_dir<0:
            sigs.append((i,'S','A' if volx>=1.5 else 'B'))
        elif (turn_l or brk_l) and obv_dir>0:
            sigs.append((i,'L','A' if volx>=1.5 else 'B'))
    return sigs

def _stoch_from_rsi(rs, n=14):
    out=[None]*len(rs)
    for i in range(n,len(rs)):
        w=[x for x in rs[i-n+1:i+1] if x is not None]
        if len(w)<n: continue
        hi,lo=max(w),min(w)
        out[i]=100*(rs[i]-lo)/(hi-lo) if hi>lo else 50.0
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
