#!/usr/bin/env python3
"""
dewa_skill.py — MODUL KURIR v7.0: konstruksi PAYLOAD JSON kontrak bos.
ROMBAK TOTAL 30 Sep 2026 (ACC user "rombak total... Titik!"):
- build_briefing lama, scalper pack (spark/kdj/stoch_rsi/obv_slope/rel_strength/
  build_extras), classify_momentum, enrich_briefing — SEMUA DIHAPUS (era v6.7).
- Sisa yang hidup: btc_bias (mata makro P36, dipakai payload macro_matrix) +
  rsi6_series (dipakai build_payload_v7 utk RSI6 realtime & spark).
- build_payload_v7 = kontrak JSON user-spec: asset / higher_tf_alignment /
  macro_matrix / smc_micro_5m / metrics (+ funding & regime konteks).
Bos = jev persona v7.0 (jev_bridge.py). FULL JEV NO-FALLBACK.
"""
import os, json

def rsi6_series(c, n=6, w=12):
    """RSI(6) sederhana + sparkline 12 bar terakhir (mata realtime bos)."""
    g=[0.0]; lo=[0.0]
    for i in range(1,len(c)):
        g.append(max(c[i]-c[i-1],0.0)); lo.append(max(c[i-1]-c[i],0.0))
    out=[]
    for i in range(n,len(c)+1):
        ag=sum(g[i-n:i])/n; al=sum(lo[i-n:i])/n or 1e-9
        out.append(100-100/(1+ag/al))
    sp=None
    if len(out)>=w:
        w_=out[-w:]; lo_=min(w_); hi_=max(w_); rng=hi_-lo_ or 1
        blocks="▁▂▃▄▅▆▇█"
        sp=''.join(blocks[min(7,int((x-lo_)/rng*7.999))] for x in w_)
    return sp, (out[-1] if out else None)

_btc_cache={'t':0,'v':None}
def btc_bias():
    """Arah BTC 5m+1h vs EMA20: UP/DOWN/MIXED. Cache 60s. Mata makro P36."""
    import time as _t, importlib.util as _iu
    now=_t.time()
    if now-_btc_cache['t']<60: return _btc_cache['v']
    try:
        if 'vg' not in globals():
            spec=_iu.spec_from_file_location('vg',os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15_grade.py'))
            g=_iu.module_from_spec(spec); spec.loader.exec_module(g); globals()['vg']=g
        def ema(v,n=20):
            k=2/(n+1); e=v[0]
            for x in v[1:]: e=x*k+e*(1-k)
            return e
        c5=[float(x[4]) for x in vg.fetch_hist_klines('BTCUSDT','5m',60)]
        c1=[float(x[4]) for x in vg.fetch_hist_klines('BTCUSDT','1h',30)]
        b5='UP' if c5[-1]>ema(c5) else 'DOWN'
        b1='UP' if c1[-1]>ema(c1) else 'DOWN'
        v={'bias':b5 if b5==b1 else ('UP' if b5=='UP' and b1=='UP' else ('DOWN' if b5=='DOWN' and b1=='DOWN' else 'MIXED')),
           'b5':b5,'b1':b1}
    except Exception:
        v={'bias':'?','b5':'?','b1':'?'}
    _btc_cache['t']=now; _btc_cache['v']=v
    return v

_CRYPTO={'BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
         'LINKUSDT','DOTUSDT','LTCUSDT','BCHUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
         'WLDUSDT','ORDIUSDT','ENAUSDT','WIFUSDT','ONDOUSDT','HYPEUSDT','JUPUSDT','RUNEUSDT',
         'AAVEUSDT','UNIUSDT','FETUSDT','GALAUSDT','CRVUSDT','LDOUSDT','ARBUSDT','OPUSDT',
         'ATOMUSDT','FILUSDT','INJUSDT','SEIUSDT','TRXUSDT'}
_METAL={'XAUUSDT':'XAUUSD','XAGUSDT':'XAGUSD','XPTUSDT':'XPTUSD','PAXGUSDT':'XAUUSD'}

def _asset_class(sym):
    if sym in _METAL: return 'TRADFI_METAL'
    if sym in _CRYPTO: return 'CRYPTO'
    return 'CRYPTO'

def build_payload_v7(sym, kk, side, grade, src, regime, funding, htf_maps):
    """KURIR v7.0 -> BOS v7.0: payload JSON kontrak (user-spec 30 Sep).
    kk: bar 5m [ts,o,h,l,c,v]; htf_maps: hr.build_htf_maps() hasil
    {'15m':{ts:(ema20,ema50)}, '1h':{...}, '1h_struct': str}.
    Blok SMC (MSS/FVG/liquidity) & market snapshot disuntik dewa_live setelah ini."""
    side='LONG' if side in ('L','LONG') else 'SHORT'
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]
    c=[r[4] for r in kk]; v=[r[5] for r in kk]
    i=len(kk)-2  # bar closed terakhir
    # RSI6 bar closed + sparkline (realtime di-upgrade dewa_live via live_px -> metrics.rsi6Realtime)
    sp, r6 = rsi6_series(c)
    r6rt=r6
    # z-score 60 bar (kontrak metrics)
    mu=sum(c[max(0,i-59):i+1])/len(c[max(0,i-59):i+1])
    sd=(sum((x-mu)**2 for x in c[max(0,i-59):i+1])/len(c[max(0,i-59):i+1]))**0.5 or 1e-9
    z=(c[i]-mu)/sd
    # volume x vs rata 20 candle
    vma=sum(v[i-19:i+1])/20 or 1e-9
    volx=v[i]/vma
    rng=h[i]-l[i]
    body=min(o[i],c[i])-l[i]; body2=h[i]-max(o[i],c[i])
    wick_lo=round(body/rng*100,1) if rng>0 else 0.0
    wick_hi=round(body2/rng*100,1) if rng>0 else 0.0
    # ===== v12.0 ANTI-FAKEOUT LENS (matematika host, bukan opini LLM) =====
    # candleAna: arah/kekuatan body; closePos: posisi close dlm range (0=di low,100=di high,
    # |closePos-50| kecil = close tengah = SINYAL LELEH/ragu); consec: bar searah beruntun
    # ( exhaustion ); retrace: seberapa jauh harga sudah mundur dr ekstrem 20-bar
    # (wick-balik = entry fakeout); bbTouch: nempel BB20 2-sd (pucuk/lembah statistik).
    candleAna=round((c[i]-o[i])/rng*100,1) if rng>0 else 0.0
    closePos=round((c[i]-l[i])/rng*100,1) if rng>0 else 50.0
    consec=0; j2=i
    if c[i]>o[i]:
        while j2>0 and c[j2]>o[j2]: consec+=1; j2-=1
    elif c[i]<o[i]:
        while j2>0 and c[j2]<o[j2]: consec+=1; j2-=1
    if side=='SHORT':
        hi20=max(h[max(0,i-19):i+1])
        retrace=round((hi20-c[i])/c[i]*100,3) if hi20 else 0.0
    else:
        lo20=min(l[max(0,i-19):i+1])
        retrace=round((c[i]-lo20)/c[i]*100,3) if lo20 else 0.0
    if i>=19:
        seg=c[i-19:i+1]; m20=sum(seg)/20
        s20=(sum((x-m20)**2 for x in seg)/20)**0.5
        bbTouch='UPPER' if c[i]>m20+2*s20 else ('LOWER' if c[i]<m20-2*s20 else 'NONE')
    else:
        bbTouch='NONE'
    # HTF alignment dari maps (15m cross + struktur 1h)
    ts=kk[i][0]
    m15=htf_maps.get('15m',{}).get(ts)
    if m15:
        tf15='BULLISH' if m15[0]>m15[1] else ('BEARISH' if m15[0]<m15[1] else 'FLAT')
    else:
        tf15='UNKNOWN'
    v1h=htf_maps.get('1h',{})
    ts1=max((t for t in v1h if t<=ts), default=None)
    volx1h=None
    if ts1:
        row=v1h[ts1]
        e20,e50=row[0],row[1]
        volx1h=row[2] if len(row)>2 else None
    cls=_asset_class(sym)
    return {
        "asset": {"class": cls, "ticker": _METAL.get(sym, sym.replace('USDT','')),
                  "rsi6Realtime": round(r6rt,1) if r6rt is not None else None},
        "side": side, "grade": grade, "engine": src,
        "higher_tf_alignment": {
            "tf_15m_ema_cross": tf15,
            "tf_1h_trend_structure": str(htf_maps.get('1h_struct','RANGING')),
            "vol_x_1h": volx1h,
        },
        "macro_matrix": {
            "btc_bias": btc_bias()['bias'],
            "btc_dominance": None,   # di-upgrade smc_engine.enrich (btcDominance)
            "dxy_bias": None,        # di-upgrade smc_engine.enrich (dxyBias, aset logam)
        },
        "smc_micro_5m": {
            "regime": regime,
            "marketStructure": None,  # di-upgrade smc_engine.enrich
            "mssLevel": None,
            "fvgStatus": None,
            "fvgRange": None,
            "liquidityPool": None,
        },
        "metrics": {
            "volx": round(volx,2),
            "zScore": round(z,2),
            "wick_ratio_pct": {"low": wick_lo, "high": wick_hi},
            "rsi6": round(r6,1) if r6 is not None else None,
            "rsi6_spark": sp,
            "freshnessMinutes": 0,
            # v7.1 ANTI-CHASE (di-upgrade dewa_live dari entryLoc host):
            # CHASE/atrDistance>3.0 -> bos WAJIB REJECT + WAIT_FOR_RETRACE_TO_FVG (P5 guard).
            "entryStatus": None, "atrDistance": None, "swingAgeBars": None,
            "candleAna": candleAna, "closePos": closePos, "consec": consec,
            "retracePct": retrace, "bbTouch": bbTouch,  # v12.0 ANTI-FAKEOUT LENS
        },
        "context": {"funding": funding, "candle": {
            "ts": kk[i][0], "o": o[i], "h": h[i], "l": l[i], "c": c[i], "volx": round(volx,2)}},
    }

if __name__=='__main__':
    # smoke offline: payload v7 utk 1 pair live (tanpa bos)
    import importlib.util as iu
    sp=iu.spec_from_file_location('vg',os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15_grade.py'))
    vg=iu.module_from_spec(sp); sp.loader.exec_module(vg)
    import hybrid_rules as hr
    kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in vg.fetch_hist_klines('BTCUSDT','5m',600)]
    maps=hr.build_htf_maps('BTCUSDT',len(kk))
    p=build_payload_v7('BTCUSDT',kk,'L','A','fade','RANGE',0.0001,maps)
    print(json.dumps(p,ensure_ascii=False)[:700])
