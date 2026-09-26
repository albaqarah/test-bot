#!/usr/bin/env python3
"""
smc_engine.py — P20: Smart Money Concepts + Money Flow untuk briefing bos (TYPESAFE SNIPER v3.5).
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
def btc_dom_trend():
    """Proxy BTC.D: share volume BTC (quote vol) vs total top-20 pair 1h.
    Share naik 2 periode = RISING. Bukan BTC.D resmi (off-chain CMC), tapi
    arah aliran uang intra-Binance — yang relevan untuk rotasi alt."""
    try:
        t = _fapi('ticker/24hr')
        if not t:
            return None
        rows = [x for x in t if x['symbol'].endswith('USDT')]
        rows.sort(key=lambda x: -float(x['quoteVolume']))
        top = rows[:20]
        btc = sum(float(x['quoteVolume']) for x in top if x['symbol'] == 'BTCUSDT')
        tot = sum(float(x['quoteVolume']) for x in top)
        share_now = btc / tot if tot else None
        # share historical approx: pakai rasio priceChangePct — BTC outperform = dominance rising
        btc_chg = float([x for x in top if x['symbol'] == 'BTCUSDT'][0]['priceChangePercent'])
        alt_chg = statistics.mean(float(x['priceChangePercent']) for x in top if x['symbol'] != 'BTCUSDT')
        if btc_chg - alt_chg > 0.5:
            trend = 'RISING'
        elif alt_chg - btc_chg > 0.5:
            trend = 'FALLING'
        else:
            trend = 'SIDEWAYS'
        return {'btcDominance': trend, 'btcChg24h': btc_chg, 'altChg24hAvg': round(alt_chg, 2),
                'btcVolShareTop20': round(share_now * 100, 1) if share_now else None}
    except Exception:
        return None

def money_flow(btc_bias, dom):
    """Matriks aliran uang (persona v3.5). btc_bias: BULLISH/BEARISH/SIDEWAYS."""
    if not dom or not btc_bias:
        return None
    d = dom.get('btcDominance')
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
        out.update(money_flow(btc_bias, dom) or {})
        out['assetClass'] = 'CRYPTO'
    return out

if __name__ == '__main__':
    print(json.dumps(enrich('RUNEUSDT', 'SIDEWAYS'), indent=1))
    print(json.dumps(enrich('XAUUSDT'), indent=1))


# ==== P21a: AUDIT TRAIL P1-P8 (faktual dari brief, bukan LLM) ====
def pipeline_log(brief, dec, conf):
    """Catat proses P1-P8 faktual tiap evaluasi bos -> dewa_live_log.jsonl via log() caller."""
    smc_d = brief.get('smc') or brief
    rsi6 = None
    v = brief.get('vision') or {}
    rsi6 = v.get('rsi6_now') or v.get('rsi6_realtime') or brief.get('rsi6_realtime')
    mf = brief.get('moneyFlow') or '-'
    if str(brief.get('source','')).lower() in ('xauusdt','xagusdt','xptusdt') or brief.get('dxyBias'):
        p1 = f"TRADFI {brief.get('symbol','?')} · DXY {brief.get('dxyBias','?')}"
    else:
        p1 = f"CRYPTO {brief.get('symbol','?')} · BTC.D {smc_d.get('btcDominance','?')}"
    try:
        budget = round(sum(p for k,p in (dec.get('probabilities') or {}).items() if 'CONFIRMED' in k), 2)
    except Exception:
        budget = None
    return {
        'event': 'pipeline_P1_P8',
        'P1_asset': p1,
        'P2_moneyflow': mf if mf != '-' else (brief.get('tradfiMoneyFlow') or smc_d.get('moneyFlow') or '-'),
        'P3_mss': smc_d.get('mss', 'NONE'),
        'P4_fvg': f"{smc_d.get('fvg','NONE')} {smc_d.get('fvgRange','') if smc_d.get('fvgRange') else ''}".strip(),
        'P5_wick': f"rsi6={rsi6}" + (" EXTREME" if isinstance(rsi6,(int,float)) and (rsi6>85 or rsi6<15) else ""),
        'P6_risk': dec.get('variant') or (max((dec.get('probabilities') or {}).items(), key=lambda x: x[1])[0]
                     if dec.get('probabilities') else '-'),
        'P7_budget': budget,
        'P8_freshness': f"{brief.get('age_min')}m" if brief.get('age_min') is not None else 'live',
        'decision': dec.get('decision'), 'conf': conf,
    }


# ==== P26: MOMENTUM BATTERY — sisa bensin gerakan (crypto & tradfi) ====
def momentum_battery(k, side=None):
    """k = list candle 5m (kolom Binance). Return dict {battery: 'FULL'|'MID'|'LOW', pct: 0-100, detail}.
    Komponen:
      1) vol_decay: volume 3 candle terakhir vs 20-bar avg — masih naik = bensin penuh
      2) room: jarak harga ke hi/lo 48-bar (sisa ruang gerak arah sinyal)
    Battery = rata-rata bobot (vol 50% + room 50%)."""
    try:
        c=[float(x[4]) for x in k]; h=[float(x[2]) for x in k]
        l=[float(x[3]) for x in k]; v=[float(x[5]) for x in k]
        n=len(c)
        if n<25: return {'battery':'MID','pct':50,'vol_ratio':None,'room_pct':None}
        # 1) volume decay 3 candle terakhir (exclude bar forming? pakai semua, pembobotan kecil)
        vavg=sum(v[-23:-3])/20
        vlast=sum(v[-3:])/3
        vol_ratio=vlast/vavg if vavg else 1.0
        vol_score=max(0.0,min(1.0,(vol_ratio-0.5)/1.5))  # 0.5x=0%, 2.0x=100%
        # 2) sisa ruang: jarak close ke ekstrem 48-bar
        win=min(n,49)
        hi48=max(h[-win:]); lo48=min(l[-win:]); px=c[-1]
        rng=hi48-lo48
        room_up=(hi48-px)/rng if rng>0 else 0.5
        room_dn=(px-lo48)/rng if rng>0 else 0.5
        if side=='LONG': room=room_up; pos_in=room_up
        elif side=='SHORT': room=room_dn; pos_in=room_dn
        else: room=max(room_up,room_dn); pos_in=room
        pct=round((0.4*vol_score+0.6*room)*100)
        # P28 anti-telat: entry nyangkut di ujung gerakan (room <25%) dgn vol tinggi = JEBAKAN chase — cap di MID (bukan FULL)
        if pos_in<0.25 and pct>=60: pct=55
        bat='FULL' if pct>=60 else ('LOW' if pct<30 else 'MID')
        return {'battery':bat,'pct':pct,'vol_ratio':round(vol_ratio,2),
                'room_pct':round(room*100,1)}
    except Exception as e:
        return {'battery':'MID','pct':50,'vol_ratio':None,'room_pct':None,'err':str(e)[:60]}


# ==== P29: REVERSAL HINT — kompas arah ekstrem (permintaan user) ====
def reversal_hint(k):
    """Baca momentum murni (tanpa sinyal): gerakan UP kuat & extended = hint SHORT (pucuk matang);
    gerakan DOWN kuat & extended = hint LONG (lembah matang). Return dict hint utk briefing."""
    try:
        c=[float(x[4]) for x in k]; h=[float(x[2]) for x in k]
        l=[float(x[3]) for x in k]; v=[float(x[5]) for x in k]
        n=len(c)
        if n<25: return {'reversalHint':'NONE'}
        vavg=sum(v[-23:-3])/20
        vlast=sum(v[-3:])/3
        vol_ratio=vlast/vavg if vavg else 1.0
        n48=min(n,289)                    # window 24 jam (288 bar 5m) — match layar user (24h hi/lo)
        hi48=max(h[-n48:]); lo48=min(l[-n48:]); px=c[-1]
        rng=hi48-lo48
        if rng<=0: return {'reversalHint':'NONE'}
        pos_in=(px-lo48)/rng              # 0=di lembah, 1=di pucuk
        move12=(px/c[-13]-1)*100          # gerakan 1 jam terakhir %
        hot=vol_ratio>=1.5 or abs(move12)>=1.5
        if pos_in>=0.90 and move12>=0 and hot:
            return {'reversalHint':'SHORT','reversalWhy':f'pucuk matang: pos {pos_in*100:.0f}% dari 24h-range, gerak 1j {move12:+.1f}%, vol {vol_ratio:.1f}x'}
        if pos_in<=0.10 and move12<=0 and hot:
            return {'reversalHint':'LONG','reversalWhy':f'lembah matang: pos {pos_in*100:.0f}% dari 24h-range, gerak 1j {move12:+.1f}%, vol {vol_ratio:.1f}x'}
        return {'reversalHint':'NONE'}
    except Exception:
        return {'reversalHint':'NONE'}
