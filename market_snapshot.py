#!/usr/bin/env python3
"""
market_snapshot.py — P32 SKILL PASAR KURIR (host-side, GRATIS, tanpa LLM).
Sumber formula: The-Quant-Trading-Vault (spec teruji ChaoZhang/TradingView) + P32_TRADE_RUBRIC.md.

10 skill (F+G doc P32):
  1  ATR14 + usulan SL dinamis (1.5xATR)          — obat SL persen mati
  2  VWAP + sigma bands (premium/discount)        — obat entry pucuk
  3  SQUEEZE (BB dalam Keltner)                   — koin tidur -> breakout
  4  ADX14 regime (chop vs trend)                 — pilih aturan fade/follow
  5  MTF 5m/15m/1h EMA20 alignment                — izin TF besar
  6  Divergence RSI6 (bearish/bullish)            — early-warning reversal
  7  Volume dry-up + climax                       — deteksi jebakan
  8  Session (WIB): ASIA/LONDON/NY                — session_fit rubric
  9  Funding + Open Interest delta                — crowded/squeeze risk
  10 Order-book imbalance (depth 100)             — dinding bid/ask
Plus WICK-HUNTER (doc F): pin/hammer/shooting-star + exhaustion osc + strength 0-100.
Semua fetch: timeout 8s + cache (depth 30s, MTF 60s, OI 60s). GAGAL = field None, TIDAK PERnah raise.
Output: enrich_market(brief, sym, kk, rs=None, i=None) -> brief (dict sama, diisi 'market'+'wickHint'+'slSuggest').
"""
import json, math, os, time, urllib.request

T0=time.time
TIMEOUT=float(os.environ.get('MKT_TIMEOUT','8'))
CACHE={'depth':{}, 'klines':{}, 'oi':{}}

def _get(url, timeout=None):
    try:
        with urllib.request.urlopen(url, timeout=timeout or TIMEOUT) as r:
            return json.load(r)
    except Exception:
        return None

def _cache_get(bucket, key, ttl, fn):
    now=T0(); hit=CACHE[bucket].get(key)
    if hit and now-hit[0]<ttl: return hit[1]
    v=fn()
    if v is not None: CACHE[bucket][key]=(now,v)
    return v

# ---------- indikator dasar (pure, tanpa fetch) ----------
def ema(v,n=20):
    if len(v)<n: return None
    k=2/(n+1); e=sum(v[:n])/n
    for x in v[n:]: e=x*k+e*(1-k)
    return e

def atr14(kk, i=None):
    """ATR14 Wilder. kk bar fapi [t,o,h,l,c,v,...]; i=index bar closed terakhir."""
    if i is None: i=len(kk)-2
    if i<15: return None
    trs=[]
    for j in range(i-13,i+1):
        h=float(kk[j][2]); l=float(kk[j][3]); pc=float(kk[j-1][4])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    a=sum(trs)/14
    for j in range(i-14,-1,-1):
        h=float(kk[j][2]); l=float(kk[j][3]); pc=float(kk[j-1][4]) if j>0 else float(kk[0][1])
        a=(a*13+max(h-l,abs(h-pc),abs(l-pc)))/14
    return a

def adx14(kk, i=None, n=14):
    """ADX Wilder 14. Return (adx, plus_di, minus_di) atau None."""
    if i is None: i=len(kk)-2
    if i<2*n+1: return None
    trs=[];pds=[];mds=[]
    for j in range(1,i+1):
        h=float(kk[j][2]);l=float(kk[j][3]);pc=float(kk[j-1][4])
        up=h-float(kk[j-1][2]); dn=float(kk[j-1][3])-l
        pds.append(up if (up>dn and up>0) else 0.0)
        mds.append(dn if (dn>up and dn>0) else 0.0)
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    atr=sum(trs[:n]); p=sum(pds[:n]); m=sum(mds[:n])
    dxs=[]
    for j in range(n,len(trs)+1):
        if j>n:
            atr=atr-atr/n+trs[j-1]; p=p-p/n+pds[j-1]; m=m-m/n+mds[j-1]
        if atr>0:
            pdi=100*p/atr; mdi=100*m/atr
            dxs.append(100*abs(pdi-mdi)/(pdi+mdi) if (pdi+mdi)>0 else 0.0)
    if len(dxs)<n: return None
    adx=sum(dxs[:n])/n
    for d in dxs[n:]: adx=(adx*(n-1)+d)/n
    pdi=100*p/atr if atr>0 else 0; mdi=100*m/atr if atr>0 else 0
    return round(adx,1), round(pdi,1), round(mdi,1)

# ---------- fetch helpers (cache) ----------
def klines(sym, interval, limit, ttl=60):
    def f():
        d=_get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval={interval}&limit={limit}")
        return d if isinstance(d,list) and len(d)>10 else None
    return _cache_get('klines', sym+interval+str(limit), ttl, f)

def depth_imb(sym):
    """Order-book imbalance depth100: (bid-ask)/(bid+ask) sekitar mid + wall terbesar."""
    def f():
        d=_get(f"https://fapi.binance.com/fapi/v1/depth?symbol={sym}&limit=100")
        if not isinstance(d,dict): return None
        bids=d.get('bids') or []; asks=d.get('asks') or []
        if not bids or not asks: return None
        mid=(float(bids[0][0])+float(asks[0][0]))/2
        bv=sum(float(x[1]) for x in bids if float(x[0])>mid*0.995)
        av=sum(float(x[1]) for x in asks if float(x[0])<mid*1.005)
        wb=max(bids,key=lambda x:float(x[1])); wa=max(asks,key=lambda x:float(x[1]))
        return {'book_imb':round((bv-av)/(bv+av),3) if (bv+av)>0 else 0.0,
                'bid_wall':round(float(wb[1]),1),'bid_wall_px':float(wb[0]),
                'ask_wall':round(float(wa[1]),1),'ask_wall_px':float(wa[0])}
    return _cache_get('depth', sym, 30, f)

def oi_delta(sym):
    """Perubahan open interest 5m terakhir (%)."""
    def f():
        d=_get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=5m&limit=2")
        if not isinstance(d,list) or len(d)<2: return None
        a=float(d[0]['sumOpenInterest']); b=float(d[-1]['sumOpenInterest'])
        return {'oi_chg_pct':round((b-a)/a*100,2) if a>0 else 0.0,'oi_now':b}
    return _cache_get('oi', sym, 60, f)

# ---------- skill utama ----------
def vwap_sigma(kk, i=None, n=96):
    """VWAP rolling n-bar (8 jam 5m) + sigma harga. Return (vwap, sigma, z)."""
    if i is None: i=len(kk)-2
    seg=kk[max(0,i-n+1):i+1]
    if len(seg)<10: return None
    pv=0.0; vv=0.0; pxs=[]
    for b in seg:
        tp=(float(b[2])+float(b[3])+float(b[4]))/3
        v=float(b[5]) or 1e-9
        pv+=tp*v; vv+=v; pxs.append(tp)
    vwap=pv/vv if vv>0 else None
    if vwap is None: return None
    m=sum(pxs)/len(pxs)
    var=sum((x-m)**2 for x in pxs)/len(pxs)
    sd=math.sqrt(var)
    last=float(kk[i][4])
    z=(last-vwap)/sd if sd>0 else 0.0
    return round(vwap,8), round(sd,6), round(z,2)

def squeeze(kk, i=None, n=20):
    """TTM-style: BB(n,2) di dalam Keltner(n,1.5xATR) = squeeze ON."""
    if i is None: i=len(kk)-2
    if i<n+2: return None
    cl=[float(kk[j][4]) for j in range(i-n+1,i+1)]
    m=sum(cl)/n
    sd=math.sqrt(sum((x-m)**2 for x in cl)/n)
    a=atr14(kk,i)
    if a is None: return None
    bb_hi,bb_lo=m+2*sd,m-2*sd
    kc_hi,kc_lo=m+1.5*a,m-1.5*a
    return {'squeeze_on':bool(bb_hi<kc_hi and bb_lo>kc_lo),
            'bb_width_pct':round((bb_hi-bb_lo)/m*100,2)}

def _rsi6(cl):
    """RSI6 Wilder lokal (self-contained, sama metode dgn reversion_bot)."""
    if len(cl)<8: return None
    gains=[];losses=[]
    for i in range(1,len(cl)):
        d=cl[i]-cl[i-1]; gains.append(max(d,0.0)); losses.append(max(-d,0.0))
    ag=sum(gains[:6])/6; al=sum(losses[:6])/6
    for i in range(6,len(gains)):
        ag=(ag*5+gains[i])/6; al=(al*5+losses[i])/6
    if al<=0: return 100.0
    rs=ag/al
    return round(100-100/(1+rs),1)

def _regime(cl):
    """Regime stack EMA20/EMA50 (definisi sama dgn reversion_bot.regime_1h).
    Return (regime, dir) — dir tetap 'UP'/'DOWN' vs EMA20 (skor rubric TIDAK berubah)."""
    e20=ema(cl,20); e50=ema(cl,50)
    if not e20 or not e50: return None, None
    c=cl[-1]
    reg='TREND_UP' if c>e20>e50 else ('TREND_DOWN' if c<e50<e20 else 'RANGE')
    d='UP' if c>e20 else 'DOWN'
    return reg, d

def mtf_align(sym, side_hint=None):
    """P32-B (ACC user 28 Sep): per TF kirim regime + rsi6 + dir — persis doc section D.
    {'5m':{'regime','rsi6','dir'}, '15m':..., '1h':..., 'score':N}
    score = jumlah TF searah side_hint (dari dir vs EMA20 — perilaku lama dipertahankan)."""
    out={}; dirs={}
    for iv in ('5m','15m','1h'):
        k=klines(sym,iv,60)
        if not k: out[iv]=None; continue
        cl=[float(b[4]) for b in k]
        reg,d=_regime(cl)
        out[iv]={'regime':reg,'rsi6':_rsi6(cl),'dir':d}
        dirs[iv]=d
    if side_hint in ('LONG','SHORT'):
        want='UP' if side_hint=='LONG' else 'DOWN'
        out['score']=sum(1 for iv in ('5m','15m','1h') if dirs.get(iv)==want)
    else: out['score']=None
    return out

def divergence_rsi6(kk, rs, i=None, look=40):
    """Divergence regular RSI6 vs harga (pivot 2-tinggi/2-rendah di look bar)."""
    if not rs or len(rs)<look+2: return None
    if i is None: i=len(kk)-2
    seg=[(float(kk[j][4]), rs[j]) for j in range(max(0,i-look),i+1) if rs[j] is not None]
    if len(seg)<10: return None
    ph=[]; pl=[]
    for j in range(2,len(seg)-2):
        px,rv=seg[j]
        if px>=seg[j-1][0] and px>=seg[j-2][0] and px>seg[j+1][0] and px>seg[j+2][0]: ph.append((px,rv))
        if px<=seg[j-1][0] and px<=seg[j-2][0] and px<seg[j+1][0] and px<seg[j+2][0]: pl.append((px,rv))
    out={'bear_div':False,'bull_div':False}
    if len(ph)>=2 and ph[-1][0]>ph[-2][0] and ph[-1][1]<ph[-2][1]: out['bear_div']=True
    if len(pl)>=2 and pl[-1][0]<pl[-2][0] and pl[-1][1]>pl[-2][1]: out['bull_div']=True
    return out

def entry_loc(kk, i=None, side=None, atr=None):
    """P38-C (ACC user 30 Sep): LOKASI entry vs swing 30-bar dlm satuan ATR.
    true = harga masuk di zona swing (<=1.5 ATR dr pucuk utk SHORT / lembah utk LONG) = premium timing;
    chase = sudah lari >3 ATR dr swing = ngejar gerakan;
    mid = di antaranya. Ukur jarak entry ke swing EXTREME searah (SHORT->swing high, LONG->swing low)
    dan umur swing (bar sejak swing terbentuk). Semua dari kk host-side (gratis)."""
    if i is None: i=len(kk)-2
    if i<32 or side not in ('LONG','SHORT'): return None
    seg=kk[i-30:i]
    if not seg: return None
    hi_j=max(range(len(seg)), key=lambda j: float(seg[j][2])); lo_j=min(range(len(seg)), key=lambda j: float(seg[j][3]))
    hi=float(seg[hi_j][2]); lo=float(seg[lo_j][3]); c=float(kk[i][4])
    if atr is None: atr=atr14(kk,i)
    if not atr or atr<=0: return None
    if side=='SHORT':
        dist=(hi-c)/atr; age=i-1-(i-30+hi_j)
    else:
        dist=(c-lo)/atr; age=i-1-(i-30+lo_j)
    loc='true' if dist<=1.5 else ('mid' if dist<=3.0 else 'chase')
    return {'loc':loc,'swing_dist_atr':round(dist,2),'swing_age_bars':age,
            'swing_px':round(hi if side=='SHORT' else lo,8)}

def session_wib():
    from datetime import datetime, timezone, timedelta
    h=datetime.now(timezone(timedelta(hours=7))).hour
    if 7<=h<14: s='ASIA'
    elif 14<=h<21: s='LONDON'
    elif 21<=h<24 or h<5: s='NEWYORK'
    else: s='OFFHOURS'
    return s

def dry_up(kk, i=None, n=20):
    """Volume kering: rata2 vol_x 3 bar terakhir < 0.6."""
    if i is None: i=len(kk)-2
    if i<n+2: return None
    vs=[float(kk[j][5]) for j in range(i-n+1,i+1)]
    m=sum(vs)/n or 1e-9
    vx3=[float(kk[j][5])/m for j in range(i-2,i+1)]
    return {'vol_x_now':round(vx3[-1],2),'dry_up':bool(sum(vx3)/3<0.6)}

# ---------- WICK-HUNTER (doc F) ----------
def wick_hunter(kk, rs=None, i=None):
    """Deteksi pin/hammer/shooting-star + exhaustion + climax. Return dict hint."""
    if i is None: i=len(kk)-2
    if i<21: return None
    b=kk[i]
    o,h,l,c=(float(b[j]) for j in (1,2,3,4)); v=float(b[5])
    rng=h-l
    if rng<=0: return None
    body=abs(c-o); uw=h-max(o,c); lw=min(o,c)-l
    a=atr14(kk,i)
    atr_pct=(a/c*100) if (a and c>0) else None
    # ATR filter: buang candle gila/abis (0.5x-2.5x ATR)
    atr_ok = atr_pct is not None and (0.5*a<=rng<=2.5*a if a else True)
    # exhaustion oscillator (Momentum-Exhaustion, ChaoZhang): ex=(CHL-MA20(CHL))/MA20
    chl=[(float(kk[j][4])+float(kk[j][2])+float(kk[j][3])) for j in range(max(0,i-39),i+1)]
    ma=sum(chl[-20:])/20
    ex_now=(chl[-1]-ma)/ma*100 if ma>0 else 0.0
    vs=[float(kk[j][5]) for j in range(i-19,i+1)]
    vma=sum(vs)/20 or 1e-9
    vol_ratio=v/vma
    climax=vol_ratio>=2.0
    # posisi close di range (fib 33.3% dari Hammer/Shooting-Star spec)
    pos=(c-l)/rng
    pattern=None; dirn='NONE'
    if atr_ok:
        if uw>=2*body and uw>=0.55*rng and c<=o+0.333*rng: pattern,dirn='shooting_star','SHORT'
        elif lw>=2*body and lw>=0.55*rng and c>=o+0.333*rng: pattern,dirn='hammer','LONG'
        elif uw>=2*body and uw>=0.55*rng: pattern,dirn='pin_up','SHORT'
        elif lw>=2*body and lw>=0.55*rng: pattern,dirn='pin_down','LONG'
    wick_dom=max(uw,lw)/rng
    ex_ref=max(2*atr_pct,0.6) if atr_pct else 2.0
    ex_score=min(1.0,abs(ex_now)/ex_ref)
    vol_score=min(1.0,vol_ratio/2.5)
    strength=int(round((0.40*wick_dom+0.20*pos + 0.25*ex_score+0.15*vol_score)*100))
    # fade melawan wick ekstrem RSI6: kalau hint searah wick-nya jelas tapi RSI6 belum ekstrem, kurangi strength
    if rs and rs[i] is not None:
        r6=rs[i]
        if dirn=='SHORT' and r6<70: strength=int(strength*0.85)
        if dirn=='LONG' and r6>30: strength=int(strength*0.85)
    return {'dir':dirn,'pattern':pattern or 'none','strength':strength,
            'wick_dom':round(wick_dom,2),'pos_in_range':round(pos,2),
            'ex_now':round(ex_now,2),'vol_ratio':round(vol_ratio,2),
            'climax':bool(climax),'atr_ok':bool(atr_ok)}

# ---------- entry point ----------
def enrich_market(brief, sym, kk, rs=None, i=None):
    """Isi brief dgn 'market' + 'wickHint' + 'slSuggest'. TIDAK PERNAH raise."""
    try:
        if i is None: i=len(kk)-2
        if i<21: return brief
        c=float(kk[i][4]); side=brief.get('side'); side='LONG' if side in('L','LONG') else 'SHORT'
        m={}
        a=atr14(kk,i); m['atr_pct']=round(a/c*100,3) if (a and c>0) else None
        if m['atr_pct']:
            # === ERA MAHA DEWA v10.0: PURE UNCLAMPED ATR ENGINE (directive 1 Okt) ===
            # Clamp 0.8-2.4% DIBONGKAR total — sl_pct murni 100% linear mengikuti volatilitas
            # asli koin (DOGE ATR 0.27% -> SL 0.40%, JUP 0.40% -> SL 0.60%; bukan lagi 0.8% statis).
            sl_pct=1.5*m['atr_pct']
            # Fallback aman TEKNIS (bukan jaring pengaman strategi): pasar mati total ->
            # SL < 0.20% dinaikkan ke 0.25% biar filter lot-size exchange gak menolak order.
            if sl_pct<0.20: sl_pct=0.25
            brief['slSuggest']={'method':'ATR14x1.5','atr_pct':m['atr_pct'],'sl_pct_suggest':round(sl_pct,2)}
        vw=vwap_sigma(kk,i)
        if vw: m['vwap'],m['vwap_sigma'],m['vwap_z']=vw
        sq=squeeze(kk,i)
        if sq: m.update(sq)
        ax=adx14(kk,i)
        if ax: m['adx'],m['pdi'],m['mdi']=ax; m['regime_strength']='TREND' if ax[0]>=20 else 'CHOP'
        try: m['mtf']=mtf_align(sym, side)
        except Exception: pass
        try: m['divergence']=divergence_rsi6(kk,rs,i)
        except Exception: pass
        try: m.update(dry_up(kk,i) or {})
        except Exception: pass
        m['session']=session_wib()
        try:
            d=depth_imb(sym)
            if d: m.update(d)
        except Exception: pass
        try:
            oi=oi_delta(sym)
            if oi: m['oi_chg_pct']=oi['oi_chg_pct']
        except Exception: pass
        try:
            # candle shape: 5 candle closed terakhir utk bos (O,H,L,C,Vx)
            vs=[float(kk[j][5]) for j in range(i-19,i+1)]
            vma=sum(vs)/20 or 1e-9
            m['candles']=[[round(float(kk[j][1]),8),round(float(kk[j][2]),8),
                           round(float(kk[j][3]),8),round(float(kk[j][4]),8),
                           round(float(kk[j][5])/vma,2)] for j in range(i-4,i+1)]
        except Exception: pass
        brief['market']=m
        try: brief['wickHint']=wick_hunter(kk,rs,i)
        except Exception: pass
        try: brief['entryLoc']=entry_loc(kk,i,side,a)
        except Exception: pass
    except Exception:
        pass
    return brief

if __name__=='__main__':
    # smoke test offline dgn data live WIFUSDT
    import importlib.util as iu
    sp=iu.spec_from_file_location('bt','backtest_v15x_final.py')
    bt=iu.module_from_spec(sp); sp.loader.exec_module(bt)
    kk=bt.fetch_hist_klines('WIFUSDT','5m',60)
    b={'symbol':'WIFUSDT','side':'LONG'}
    enrich_market(b,'WIFUSDT',kk)
    print(json.dumps({'market':b.get('market'),'wickHint':b.get('wickHint'),'slSuggest':b.get('slSuggest')},indent=1))
