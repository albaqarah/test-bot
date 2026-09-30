#!/usr/bin/env python3
"""
smc_engine.py — v7.0: Smart Money Concepts + Money Flow utk payload bos (persona v7.0).
Hitung dari data Binance murni (tanpa API eksternal wajib):
  - mss: Market Structure Shift (close-candle menembus swing high/low terakhir)
  - fvg: Fair Value Gap (celah 3-candle) status + range
  - liquidity: SWEPT bila 5-60 bar terakhir menembus high/low 100 bar sebelumnya
  - btc_dom_trend: proxy BTC dominance dari share volume BTC 1h (RISING/FALLING/SIDEWAYS)
  - dxy_bias: via tv_bridge (best-effort) — hanya dipakai untuk TradFi metal
Semua best-effort: exception → nilai None (bos diajak ragu, bukan crash).
"""
import json, statistics, urllib.request
import os

TRADFI = {'XAUUSDT', 'XAGUSDT', 'XPTUSDT'}  # PAXG = crypto-ekosistem (ikut modul crypto)

def _fapi(path, params=''):
    try:
        d = json.loads(urllib.request.urlopen(
            f'https://fapi.binance.com/fapi/v1/{path}{params}', timeout=8).read())
        return d
    except Exception:
        return None

def klines(sym, interval='5m', limit=120):
    d = _fapi('klines', f'?symbol={sym}&interval={interval}&limit={limit}')
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in d] if d else None

# ---------- MSS ----------
def detect_mss(kk):
    """kk: list [o,h,l,c,vol]. MSS LONG: close menembus swing high terakhir;
    SHORT: close di bawah swing low terakhir. Swing = fractal 2-2 (2 bar kiri/kanan)."""
    try:
        c = [b[3] for b in kk]; h = [b[1] for b in kk]; l = [b[2] for b in kk]
        n = len(c)
        highs, lows = [], []
        for i in range(2, n - 2):
            if h[i] >= h[i-1] and h[i] >= h[i-2] and h[i] >= h[i+1] and h[i] >= h[i+2]:
                highs.append((i, h[i]))
            if l[i] <= l[i-1] and l[i] <= l[i-2] and l[i] <= l[i+1] and l[i] <= l[i+2]:
                lows.append((i, l[i]))
        last_close = c[-1]
        mss = None; level = None
        # cari swing high terakhir SEBELUM 2 bar terakhir (mencegah swing = bar close sendiri)
        sh = [x for x in highs if x[0] < n - 2]
        sl = [x for x in lows if x[0] < n - 2]
        if sh:
            i, px = sh[-1]
            if last_close > px:
                mss = 'MSS_BULLISH'; level = px
        if sl and mss is None:
            i, px = sl[-1]
            if last_close < px:
                mss = 'MSS_BEARISH'; level = px
        # ===== [v7.2.1 ATR BARRIER - STRICT MSS PENETRATION] =====
        # Penembusan secuil (INJ 3-tick / LTC ~0.3% 30 Sep: 'MSS✅' tapi makan SL pas
        # market flip) = BUKAN MSS. WAJIB jarak di luar swing level >= 0.25*ATR14.
        # Data ATR tak cukup = fail-closed -> NONE (searah FINAL SEAL v7.2).
        def _atr14_bars(bars):
            n_=len(bars)
            if n_ < 15: return None
            trs=[]
            for j in range(1, n_):
                hl=bars[j][1]-bars[j][2]
                hc=abs(bars[j][1]-bars[j-1][3]); lc=abs(bars[j][2]-bars[j-1][3])
                trs.append(max(hl,hc,lc))
            return sum(trs[-14:])/14.0
        if mss:
            _atr=_atr14_bars([[b[0],b[1],b[2],b[3]] for b in kk])
            _pen=abs(last_close-level) if level is not None else 0.0
            if _atr is None or _pen < 0.25*_atr:
                mss = 'NONE'; level = None   # MSS palsu / tak terbukti = NONE
        struct = 'BULLISH_Structure' if (sh and sl and sh[-1][1] >= sl[-1][1] and c[-1] > c[max(0, n - 12)]) else 'BEARISH_Structure'
        if mss:
            struct = mss.replace('MSS_', 'MSS_CONFIRMED_')
        elif sh and sl:
            struct = 'BULLISH_Structure' if sh[-1][1] - c[-1] < c[-1] - sl[-1][1] else 'BEARISH_Structure'
        return {'marketStructure': struct or 'CHoCH', 'mss': mss or 'NONE', 'mssLevel': level}
    except Exception:
        return {'marketStructure': None, 'mss': None, 'mssLevel': None}

# ---------- FVG ----------
def detect_fvg(kk, max_age=20):
    """FVG bullish: low[3] > high[1] (celah antara ekor candle 1 dan 3).
    Status MITIGATED bila harga sudah pernah masuk kembali ke gap."""
    try:
        out = {'fvgStatus': 'NONE', 'fvgRange': None}
        cands = []
        n = len(kk)
        for i in range(n - 3, 1, -1):
            h1 = kk[i-2][1]; l3 = kk[i][2]   # candle 1: i-2, candle 3: i
            if l3 > h1:
                cands.append(('BULL', h1, l3, i))
            h3 = kk[i][1]; l1 = kk[i-2][2]
            if h3 < l1:
                cands.append(('BEAR', h3, l1, i))
            if len(cands) >= 3:
                break
        if not cands:
            return out
        typ, top, bot, age_idx = cands[0]
        # mitigated? harga sesudah terbentuk gap pernah masuk ke range
        mitigated = any(kk[j][2] <= top and kk[j][1] >= bot for j in range(age_idx + 1, n))
        out['fvgStatus'] = 'MITIGATED' if mitigated else 'FORMED'
        out['fvgRange'] = [round(min(bot, top), 8), round(max(bot, top), 8)]
        out['fvgType'] = typ
        return out
    except Exception:
        return {'fvgStatus': None, 'fvgRange': None}

# ---------- Liquidity ----------
def detect_liquidity(kk):
    try:
        h = [b[1] for b in kk]; l = [b[2] for b in kk]
        n = len(kk)
        if n < 120:
            return {'liquidityPool': 'INTACT'}
        base_h = max(h[-100:-60]); base_l = min(l[-100:-60])
        swept_h = any(x > base_h for x in h[-60:])
        swept_l = any(x < base_l for x in l[-60:])
        return {'liquidityPool': 'SWEPT' if (swept_h or swept_l) else 'INTACT',
                'sweptSide': 'HIGH' if swept_h else ('LOW' if swept_l else None),
                'baseHigh': base_h, 'baseLow': base_l}
    except Exception:
        return {'liquidityPool': None}

# ---------- BTC Dominance proxy ----------
_dom_cache={'t':0.0,'v':None}
_TOP=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','BNBUSDT','ADAUSDT','LINKUSDT',
      'LTCUSDT','DOTUSDT','AVAXUSDT','SUIUSDT']
def _dom_from_rows(rows):
    """Matematika BTC.D dari rows ticker (full atau satuan)."""
    rows=[x for x in rows if x['symbol'].endswith('USDT')]
    rows.sort(key=lambda x: -float(x['quoteVolume']))
    top=rows[:20]
    if len(top)<6 or not any(x['symbol']=='BTCUSDT' for x in top): return None
    btc=sum(float(x['quoteVolume']) for x in top if x['symbol']=='BTCUSDT')
    tot=sum(float(x['quoteVolume']) for x in top)
    share_now=btc/tot if tot else None
    btc_chg=float([x for x in top if x['symbol']=='BTCUSDT'][0]['priceChangePercent'])
    alt_chg=statistics.mean(float(x['priceChangePercent']) for x in top if x['symbol']!='BTCUSDT')
    if btc_chg-alt_chg>0.5: trend='RISING'
    elif alt_chg-btc_chg>0.5: trend='FALLING'
    else: trend='SIDEWAYS'
    return {'btcDominance':trend,'btcChg24h':btc_chg,'altChg24hAvg':round(alt_chg,2),
            'btcVolShareTop20':round(share_now*100,1) if share_now else None}

def btc_dom_trend():
    """Proxy BTC.D: share volume BTC (quote vol) vs top-20 pair. 
    P36: (1) cache 60 dtk — dulu fetch penuh PER KANDIDAT tanpa cache;
    (2) fallback ticker satuan (weight 1/ea) — ticker/24hr penuh weight ~40 gampang
    kena 429/418 pas IP sibuk scan 41 pair (bos jadi buta '?' — kasus 16:32);
    (3) gagal total = 10 dtk lagi coba lagi, selagi balikin nilai cache terakhir."""
    import time as _t
    now=_t.time()
    if now-_dom_cache['t']<60: return _dom_cache['v']
    try:
        t=_fapi('ticker/24hr')
        if t:
            v=_dom_from_rows(t)
            if v:
                _dom_cache['v']=v; _dom_cache['t']=now
                return v
        # fallback ringan: 12 ticker satuan (total weight 12 vs 40)
        rows=[]
        for s in _TOP:
            d=_fapi(f'ticker/24hr?symbol={s}')
            if d: rows.append(d)
        v=_dom_from_rows(rows)
        if v:
            _dom_cache['v']=v; _dom_cache['t']=now
            return v
    except Exception:
        pass  # malformed row / jaringan = jangan bunuh enrich (dulu 1 exception = SMC hilang total)
    _dom_cache['t']=now-50  # gagal: coba lagi dlm 10 dtk
    return _dom_cache['v']

def money_flow(btc_bias, dom):
    """Matriks aliran uang (persona v3.5). btc_bias: BULLISH/BEARISH/SIDEWAYS.
    P36: BTC.D gagal fetch = anggap SIDEWAYS (jangan buang bias bos cuma krn 1 endpoint
    down — dulu dom None = matrix ikut kosong total)."""
    if not btc_bias:
        return None
    d = (dom or {}).get('btcDominance') or 'SIDEWAYS'
    table = {
        ('BULLISH', 'RISING'):  'FOKUS BTC LONG — uang tersedot ke BTC, alt cenderung diam/turun',
        ('BULLISH', 'FALLING'): 'FOKUS LONG ALTCOINS — altseason mini, momentum terbaik',
        ('BEARISH', 'RISING'):  'FOKUS SHORT ALTCOINS — alt longsor lebih dalam dr BTC',
        ('BEARISH', 'FALLING'): 'SHORT BIAS TOTAL — uang keluar dr crypto sepenuhnya (alts longsor, BTC juga tekanan)',
        ('SIDEWAYS', 'FALLING'):'FOKUS LONG ALTCOINS — BTC tenang, rotasi modal ke alts',
        ('SIDEWAYS', 'RISING'): 'BIAS BTC/NETRAL — uang masuk BTC, alt butuh konfirmasi mikro kuat',
        ('SIDEWAYS', 'SIDEWAYS'):'STRUKTUR INTERNAL SAJA — makro gak kasih arah',
        ('BEARISH', 'SIDEWAYS'):'SHORT BIAS ALTS — BTC lemah & dominan gak turun = alts gak dapat rotasi',
        ('BULLISH', 'SIDEWAYS'):'LONG BIAS HATI-HATI — BTC kuat tapi rotasi belum jalan',
    }
    return {'moneyFlow': table.get((btc_bias, d))}

# ---------- DXY (TradFi) ----------
def dxy_bias():
    """Best-effort via tv_bridge: DXY 1h EMA20 vs EMA50. Gagal → SIDEWAYS."""
    try:
        import subprocess
        out = subprocess.run(['node', os.path.join(os.path.dirname(os.path.abspath(__file__)),'tv_bridge.js'), 'TVC:DXY'],
                             capture_output=True, text=True, timeout=40)
        d = json.loads(out.stdout)
        tf60 = d.get('tf60', {}).get('ta', {})
        e20, e50 = tf60.get('ema20'), tf60.get('ema50')
        if e20 is None or e50 is None:
            return {'dxyBias': 'SIDEWAYS'}
        diff = (e20 - e50) / e50 * 100
        bias = 'BULLISH' if diff > 0.05 else ('BEARISH' if diff < -0.05 else 'SIDEWAYS')
        return {'dxyBias': bias, 'dxyEma20_50SpreadPct': round(diff, 3)}
    except Exception:
        return {'dxyBias': 'SIDEWAYS'}

def tradfi_money_flow(dxy):
    if not dxy or not dxy.get('dxyBias'):
        return None
    b = dxy['dxyBias']
    table = {
        'BULLISH':  'FOKUS SHORT LOGAM — dolar menguat, XAU/XAG/XPT melemah',
        'BEARISH':  'FOKUS LONG LOGAM — dolar melemah, logam mulia didorong naik',
        'SIDEWAYS': 'STRUKTUR INTERNAL SAJA — DXY gak kasih arah',
    }
    return {'tradfiMoneyFlow': table.get(b)}

# ---------- Entry point ----------
def enrich(sym, btc_bias=None):
    """Return dict SMC+macro utk briefing bos. Symmetric best-effort."""
    kk = klines(sym)
    if not kk:
        return {}
    out = {}
    out.update(detect_mss(kk))
    out.update(detect_fvg(kk))
    out.update(detect_liquidity(kk))
    if sym in TRADFI:
        dxy = dxy_bias()
        out.update(dxy)
        out.update(tradfi_money_flow(dxy) or {})
        out['assetClass'] = 'TRADFI_METAL'
    else:
        dom = btc_dom_trend()
        out.update(dom or {})
        # P36 FIX: kurir ngirim arah harga (UP/DOWN/MIXED/'?') tapi tabel money_flow
        # butuh BULLISH/BEARISH -> selalu None, persona langkah 2 (MONEY-FLOW MATRIX)
        # mati senyap sejak P20 (2.524 audit: mf kosong 100%). Normalisasi di sini.
        # CATATAN: param = btc_bias (jangan 'bias' — sempat NameError senyap, semua SMC mati!)
        _b = btc_bias.get('bias') if isinstance(btc_bias, dict) else btc_bias
        _m = {'UP':'BULLISH','DOWN':'BEARISH'}
        _bn = _m.get(_b if isinstance(_b,str) else '', 'SIDEWAYS')
        out.update(money_flow(_bn, dom) or {})
        out['assetClass'] = 'CRYPTO'
    return out

if __name__ == '__main__':
    print(json.dumps(enrich('RUNEUSDT', 'SIDEWAYS'), indent=1))
    print(json.dumps(enrich('XAUUSDT'), indent=1))
