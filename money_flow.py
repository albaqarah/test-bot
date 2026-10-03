# money_flow.py — v12.4 MATA UANG: sensor aliran uang real (A+B+C, fail-open total)
# A TakerFlow/CVD : dari klines 5m yang SUDAH ke-fetch (kolom 5=vol, 9=takerBuyBase) — NOL API baru
# B OpenInterest  : /futures/data/openInterestHist  (uang yang beneran megah posisi, cache 5m)
#   TopTrader L/S : /futures/data/topLongShortPositionRatio (posisi player gede, cache 5m)
# C Orderbook     : /fapi/v1/depth imbalance bid/ask ±0.5% mid + spread (cache 30 dtk)
# Falsafah: kompas buat bos jev, BUKAN gate — semua None = data gak tersedia, bos tetap ditanya.
import json, time, urllib.request

_TTL_SLOW=300*1000   # OI & top-trader: granularitas 5m → cache 5 menit
_TTL_OB=30*1000      # orderbook: fresh di momen keputusan
_cache_oi={}; _cache_tt={}; _cache_ob={}

def _get(url, timeout=6):
    req=urllib.request.Request(url, headers={'User-Agent':'dewa-sniper/12.4'})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def taker_flow(kl, lookback=30):
    """A: rasio taker-buy + streak dominan dari klines yang udah ada. NOL API."""
    try:
        rows=list(kl[-lookback:])
        if len(rows)<5: return None
        tb=sum(float(r[9]) for r in rows); tv=sum(float(r[5]) for r in rows)
        if tv<=0: return None
        streak=0
        for r in reversed(rows):
            v=float(r[5])
            if v<=0: break
            if float(r[9])/v>=0.5: streak+=1
            else: break
        return {'taker_buy_ratio':round(tb/tv,3),'streak_bars':streak,'bars':len(rows)}
    except Exception:
        return None

def open_interest(sym, now_ms):
    """B1: OI (nilai USDT) + perubahan 15m & 1 jam. Fail-open None."""
    c=_cache_oi.get(sym)
    if c and now_ms-c['ts']<_TTL_SLOW: return c['v']
    try:
        h=_get(f'https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=5m&limit=13')
        if not h: v=None
        else:
            cur=float(h[-1]['sumOpenInterestValue'])
            o15=float(h[-4]['sumOpenInterestValue']) if len(h)>=4 else cur
            o60=float(h[0]['sumOpenInterestValue'])
            v={'oi_usdt':round(cur),
               'chg_15m_pct':round((cur-o15)/o15*100,2) if o15 else 0.0,
               'chg_1h_pct':round((cur-o60)/o60*100,2) if o60 else 0.0}
        _cache_oi[sym]={'ts':now_ms,'v':v}; return v
    except Exception:
        _cache_oi[sym]={'ts':now_ms,'v':None}; return None

def top_trader(sym, now_ms):
    """B2: top-trader long/short POSITION ratio (20% akun teratas, volume terbesar). Fail-open None."""
    c=_cache_tt.get(sym)
    if c and now_ms-c['ts']<_TTL_SLOW: return c['v']
    try:
        h=_get(f'https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={sym}&period=5m&limit=3')
        if not h: v=None
        else:
            la=float(h[-1]['longAccount']); lp=float(h[-2]['longAccount']) if len(h)>1 else la
            v={'ls_top':round(float(h[-1]['longShortRatio']),2),
               'long_share_chg':round((la-lp)*100,2)}
        _cache_tt[sym]={'ts':now_ms,'v':v}; return v
    except Exception:
        _cache_tt[sym]={'ts':now_ms,'v':None}; return None

def orderbook(sym, now_ms):
    """C: imbalance bid/ask ±0.5% mid (>0.5 = bid berat) + spread bps. Cache 30 dtk. Fail-open None."""
    c=_cache_ob.get(sym)
    if c and now_ms-c['ts']<_TTL_OB: return c['v']
    try:
        d=_get(f'https://fapi.binance.com/fapi/v1/depth?symbol={sym}&limit=100')
        bids=[(float(p),float(q)) for p,q in d.get('bids',[])]
        asks=[(float(p),float(q)) for p,q in d.get('asks',[])]
        if not bids or not asks: v=None
        else:
            mid=(bids[0][0]+asks[0][0])/2
            bv=sum(q for p,q in bids if p>=mid*0.995)
            av=sum(q for p,q in asks if p<=mid*1.005)
            v={'ob_imbalance':round(bv/(bv+av),3) if bv+av else 0.5,
               'spread_bps':round((asks[0][0]-bids[0][0])/mid*10000,1)}
        _cache_ob[sym]={'ts':now_ms,'v':v}; return v
    except Exception:
        _cache_ob[sym]={'ts':now_ms,'v':None}; return None

def read_all(sym, kl5, now_ms):
    """Gabung A+B+C → dict buat brief['moneyFlowReal']. Verdict dominan 4-kotak:
    OI naik + taker beli  = LONG_LEGIT · OI turun + taker jual = SHORT_LEGIT
    OI turun + taker beli = COVER_FADE_RISK (jebakan covering) · sisanya PRESSURE_WEAK."""
    out={'taker':taker_flow(kl5),'oi':open_interest(sym,now_ms),
         'top':top_trader(sym,now_ms),'ob':orderbook(sym,now_ms)}
    try:
        t=out.get('taker') or {}; oi=out.get('oi') or {}
        if not oi or 'chg_15m_pct' not in oi: out['dominance']='OI_NA'
        else:
            up=(t.get('taker_buy_ratio',0.5)>0.5); oi_up=oi.get('chg_15m_pct',0)>0
            out['dominance']=('LONG_LEGIT' if up and oi_up else
                              'SHORT_LEGIT' if (not up) and (not oi_up) else
                              'COVER_FADE_RISK' if up else 'PRESSURE_WEAK')
    except Exception:
        out['dominance']=None
    return out
