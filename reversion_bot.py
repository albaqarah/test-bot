#!/usr/bin/env python3
"""
reversion_bot.py — PRIMITIF INDIKATOR (v7.0, rombak total 30 Sep 2026).
Engine fade lama (gen_signals RSI25/75+imb), simulate, backtest __main__ — DIHAPUS
(suplai kandidat sekarang 100% hybrid_rules v7: FADE CLIMAX / SCALP / TREND PULLBACK).
Yang dipertahankan = primitif yang dipakai pipeline live:
  rsi6       : RSI(6) Wilder — satu-satunya RSI di seluruh pipeline (mandat user)
  zscore     : z-score 200 bar
  regime_1h  : TREND_UP / TREND_DOWN / RANGE dari EMA20/50 1h
  ema_series : util EMA
"""
import importlib.util, os

spec=importlib.util.spec_from_file_location('vg',os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15_grade.py'))
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)


def ema_series(vals,n):
    k=2/(n+1); out=[vals[0]]
    for v in vals[1:]: out.append(v*k+out[-1]*(1-k))
    return out


def zscore(closes, look=200):
    out=[None]*len(closes)
    for i in range(look,len(closes)):
        w=closes[i-look:i]
        m=sum(w)/look
        var=sum((x-m)**2 for x in w)/look
        sd=var**0.5
        out[i]=(closes[i]-m)/sd if sd>0 else 0.0
    return out


def regime_1h(sym):
    try:
        k1h=vg.fetch_hist_klines(sym,'1h',300)
        c=[float(x[4]) for x in k1h]
        e20,e50=ema_series(c,20)[-1],ema_series(c,50)[-1]
        if c[-1]>e20>e50: return 'TREND_UP'
        if c[-1]<e20<e50: return 'TREND_DOWN'
        return 'RANGE'
    except Exception:
        return 'RANGE'


def rsi6(c, n=6):
    """RSI cepat ala layar scalper (Wilder) — P29: satu-satunya RSI di pipeline."""
    out=[None]*len(c); g=l2=0.0
    for i in range(1,n+1):
        dd=c[i]-c[i-1]; g+=max(dd,0); l2+=max(-dd,0)
    ag,al=g/n,l2/n; out[n]=100-100/(1+ag/al) if al else 100.0
    for i in range(n+1,len(c)):
        dd=c[i]-c[i-1]; ag=(ag*(n-1)+max(dd,0))/n; al=(al*(n-1)+max(-dd,0))/n
        out[i]=100-100/(1+ag/al) if al else 100.0
    return out
