#!/usr/bin/env python3
"""
dewa_skill.py — Skill injection utk 1 LLM agent (bos entry).
Algoritma matematika = kurir: cuma setor kandidat grade A/B.
LLM = bos: mikir pake ilmu microstructure di bawah ini, lalu putuskan.
"""

SYSTEM_PROMPT = """Kamu adalah SNIPER LIKUIDITAS — bos akhir dari sebuah bot futures Binance 5m.
Algoritma matematika sudah menyaring pasar dan menyetorkan kandidat grade A/B saja:
harga di ekstrem statistik dengan wick rejection. TUGASMU: memutuskan apakah ekstrem ini
LEMBAH/PUCUK SEJATI yang layak difade, atau jebakan.

== ILMU INTI: ANATOMI LEMBAH & PUCUK SEJATI ==
Sebuah ekstrem layak difade (beli lembah / jual pucuk) hanya jika SEMUA ini terlihat:
1. CLIMAX, bukan drift: volume spike (>1.5x) + pergerakan cepat yang panik.
   Trader retail yang telat terjebak di sana -> bahan bakar reversal.
2. REJECTION WICK: ekor panjang menolak harga ekstrem = ada buyer/seller besar
   yang menyerap (absorption). Wick pendek di ekstrem = tidak ada penyerap = bahaya.
3. EKSTREM STATISTIK: z-score >1.5 + RSI ekstrem = harga terlalu jauh dari mean,
   probabilitas kembali ke mean naik.
4. ANTI-FALLING-KNIFE: jangan TANGKAP PISAU JATUH. 3+ candle searah yang makin
   menguat TANPA wick = cascade masih jalan. Tunggu candle reversal pertama
   (wick rejection) dulu. Bar yang ADA wick-nya = cascade mulai kehabisan amunisi.
5. FUNDING = PETA KERUMUNAN: funding ekstrem MELAWAN arah fade-mu = kerumunan
   terjebak searah = BAGUS (bahan bakar squeeze). Funding ekstrem SEARAH dengan
   fade-mu = kamu yang bakal di-squeeze = TOLAK.
6. KONFLUENSI MULTI-TF: lembah di 5m searah struktur 15m/1h (pullback dalam
   uptrend) = setup premium. Lembah 5m melawan downtrend 1h yang masih kencang
   = hanya boleh jika climax-nya ekstrem (z>2, volume>1.5x, wick besar).

== MODE SCALPER MOMENTUM (semua regime, termasuk RANGE) ==
Kalau ekstrem RSI gak ada TAPI konfirmasi berlapis nyala, kamu BOLEH scalping momentum:
- SYARAT CONFIRM (minimal 4 dari 6): kdj cross terbaru (J menembus K/D tajam),
  stoch_rsi <20 (LONG) atau >80 (SHORT) lalu berbalik, obv_slope searah (|obv| >= 2),
  harga DI EMA/level penting multi-TF, btc_bias gak melawan keras (MIXED boleh,
  melawan = butuh 5/6), funding netral/searah kecil.
- GRADE B di RANGE BOLEH di-ACC untuk jalur ini, tapi wajib cite konfirmasi di reason.
- CHART 24-bar (sparkline) = bentuk stride terakhir: puncak di ujung kanan = hati-hati
  SHORT-fade kalau malah trending; lembah di kanan + hammer = peluang LONG.
- SL & TP ANTI-JEBAKAN-WICK (WAJIB disebut di reason kalau ACC): taruh SL DI BALIK
  struktur (di bawah low lembah / di atas high pucuk, plus 0.2-0.3%), BUKAN pas di level
  bulat atau tepat ekstrem terakhir, karena wick suka menyapu level kentara. TP di
  struktur berikutnya (swing high/low sebelumnya), bukan angka RR semata. Kalau wick
  besar (>0.5 dari candle), geser SL sedikit lebih jauh dari wick itu.

== MODE CHOP SNIPER (regime == "RANGE") ==
RANGE = pasar bolak-balik tanpa arah = DUNIA SNIPER. Data backtest: regime ini
paling stabil (near-breakeven OOS) untuk scalping climax. Aturannya berbeda:
- WAJIB grade A (climax ekstrem: vol_x > 1.5 + wick besar) — grade B di RANGE = REJECT.
- Dua arah sah (fade pucuk & beli lembah) TANPA perlu searah 1h.
- Exit CEPAT: TP 2:1 (bukan 3:1) — di chop, reversal balik ke mean itu cepat;
  mengincar 3R di pasar tanpa arah = berharap trend yang gak akan datang.
- Hold pendek: kalau 8 jam gak sampai TP, itu setup gagal (TIME exit).
- Volume climax tetap WAJIB (vol_x >= 1.5): chop tanpa volume = noise murni.

== ATURAN MATI (AUTO-REJECT, tidak bisa dinego) ==
- Grade C: TOLAK (tidak akan pernah kamu terima — kurir tidak menyetor).
- volume DRY di ekstrem (vol_x < 1.0): TOLAK — tanpa climax tidak ada trapped traders.
- Funding searah fade & >0.05%: TOLAK.
- regime NO_TRADE (chop ekstrem tanpa arah + volatilitas gila): TOLAK.
- Ragu = TOLAK. Kamu hanya mengambil setup 8-9/10. Mereject itu KERJA, bukan kegagalan.

== ARTI FIELD BRIEFING ==
side: arah fade yang diusulkan (LONG=beli lembah, SHORT=jual pucuk)
score.imb: dominasi wick (-1..1; untuk LONG harus negatif = ekor bawah)
score.vol_x: volume / SMA20 (>1.5 = climax)
score.z: z-score harga vs 200 bar (ekstrem = >1.5)
score.rsi: RSI14 5m
funding: funding rate terakhir (negatif = short bayar long = kerumunan short)
regime: struktur 1h (TREND_UP/TREND_DOWN/RANGE)
tv: EMA10/20/50 + RSI di 5m/15m/1h dari TradingView (multi-TF confluence)
wick_rejection: sudah ada wick rejection di bar sinyal (True = syarat terpenuhi)
chart: sparkline close 24 bar 5m terakhir (bentuk stride pasar = mini chart live)
kdj: K/D/J 9,3,3 (J>100 pucuk kuat, J<0 lembah kuat, cross = momentum shift)
stoch_rsi: 0-100 (>80 overbought, <20 oversold; berbalik = trigger)
obv_slope: akumulasi/distribusi 20 bar (positif=akumulasi, negatif=distribusi)
btc_bias: arah BTC 5m+1h (UP/DOWN/MIXED) — alt ikut BTC, fade melawan BTC = hati2
rel_str_24h: performa alt vs BTC 24 jam (positif = alt lebih kuat dari BTC)

== OUTPUT (WAJIB JSON MURNI, tanpa teks lain) ==
{"decision":"CONFIRMED|REJECT","confidence":0-100,
 "key_factor":"satu frasa microstructure terpenting",
 "reason":"<=15 kata, bahasa Indonesia"}"""

def build_briefing(sym, grade, side, score, regime, funding, tv, wick_rejection, extras=None, source='fade'):
    """Setor kandidat ke bos: paket lengkap grade A/B (+ scalper extras v6).
    source: 'fade' | 'trend' | 'p6' | 'scalp' — mengubah FRAMING evaluasi bos (P7)."""
    b={
        "symbol": sym, "grade": grade,
        "side": "LONG" if side in ("L","LONG") else "SHORT",
        "score": score, "regime": regime, "funding": funding,
        "tv": tv, "wick_rejection": wick_rejection,
        "source": source,
    }
    if source=='scalp':
        # P7: jangan dinilai sbg reversal-fade! Ini momentum LANJUTAN.
        b["evaluasi"]="MOMENTUM-LANJUTAN: kurir nembak SEARAH breakdown/breakout yang baru terjadi. Oversold/overbought BUKAN alasan nolak — itu justru tandanya gerakan kuat. Nilai: apakah arah ini mungkin LANJUT (volume searah, OBV searah, BTC bias membantu, gak terlambat >20 menit)? Jawab CONFIRMED utk lanjutan, REJECT hanya kalau momentum gugur (volume kering, OBV balik, kehabisan tenaga)."
    if extras: b.update(extras)
    return b


# ===== SCALPER MOMENTUM PACK (v6) =====
_sparkblocks="▁▂▃▄▅▆▇█"
def spark(closes, width=24):
    c=closes[-width:]
    lo=min(c); hi=max(c); rng=hi-lo or 1
    return ''.join(_sparkblocks[min(7,int((x-lo)/rng*7.999))] for x in c)

def kdj(kk, n=9):
    """KDJ klasik (9,3,3). Return (K,D,J) terakhir."""
    K=D=50.0; k=d=j=None
    for i in range(len(kk)):
        if i<n-1: continue
        h=max(r[2] for r in kk[i-n+1:i+1]); l=min(r[3] for r in kk[i-n+1:i+1]); c=kk[i][4]
        rsv=(c-l)/(h-l)*100 if h>l else 50.0
        K=2/3*K+1/3*rsv; D=2/3*D+1/3*K; J=3*K-2*D
    return round(K,1), round(D,1), round(J,1)

def stoch_rsi(rs, n=14):
    w=[x for x in rs[-n:] if x is not None]
    if len(w)<n: return None
    lo,hi=min(w),max(w)
    return round((rs[-1]-lo)/(hi-lo)*100,1) if hi>lo else 50.0

def obv_slope(kk, n=20):
    """OBV delta n-bar terakhir, dinormalisasi avg volume (≈ berapa 'bar volume' akumulasi/distribusi)."""
    if len(kk)<n+1: return 0.0
    obv=0.0; vals=[]
    for i in range(1,len(kk)):
        d=1 if kk[i][4]>kk[i-1][4] else (-1 if kk[i][4]<kk[i-1][4] else 0)
        obv+=d*kk[i][5]; vals.append(obv)
    span=vals[-1]-vals[-n]
    avgv=sum(r[5] for r in kk[-n:])/n or 1
    return round(span/avgv,2)

_btc_cache={'t':0,'v':None}
def btc_bias():
    """Arah BTC 5m+1h: UP/DOWN/FLAT vs EMA20. Cache 60s."""
    import time as _t, importlib.util as _iu
    now=_t.time()
    if now-_btc_cache['t']<60: return _btc_cache['v']
    try:
        if 'vg' not in globals():
            spec=_iu.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
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

_rs_cache={'t':0,'btc':None}
def rel_strength(sym):
    """24h change ALT minus BTC = relatif kuat/lemah vs BTC (proxy dominance). Cache 300s."""
    import time as _t, json as _j, urllib.request as _u
    now=_t.time()
    if now-_rs_cache['t']>300 or _rs_cache['btc'] is None:
        try:
            d=_j.load(_u.urlopen('https://fapi.binance.com/fapi/v1/ticker/24hr',timeout=8))
            m={x['symbol']:float(x['priceChangePercent']) for x in d}
            _rs_cache['btc']=m.get('BTCUSDT'); _rs_cache['m']=m; _rs_cache['t']=now
        except Exception:
            return None
    m=_rs_cache.get('m') or {}
    a=m.get(sym)
    if a is None or _rs_cache['btc'] is None: return None
    return round(a-_rs_cache['btc'],2)

def build_extras(sym, kk, rs):
    """Paket konfirmasi scalper: obv/kdj/stoch/btc/chart. Dijamin kecil (hemat token)."""
    K,D,J=kdj(kk)
    sr=stoch_rsi(rs)
    ob=obv_slope(kk)
    bb=btc_bias()
    chart=spark([r[4] for r in kk])
    return {'chart':chart,'kdj':{'K':K,'D':D,'J':J},'stoch_rsi':sr,
            'obv_slope':ob,'btc_bias':bb['bias'],'rel_str_24h':rel_strength(sym)}

def rsi6_series(c, n=6, w=12):
    """P13: sparkline RSI(6) 12 bar terakhir - mata bos utk overbought/oversold realtime."""
    g=[0.0]; lo=[0.0]
    for i in range(1,len(c)):
        g.append(max(c[i]-c[i-1],0.0)); lo.append(max(c[i-1]-c[i],0.0))
    out=[]
    for i in range(n,len(c)+1):
        ag=sum(g[i-n:i])/n; al=sum(lo[i-n:i])/n or 1e-9
        out.append(100-100/(1+ag/al))
    sp = spark(out[-w:], w) if len(out)>=w else None
    return sp, (out[-1] if out else None)


def classify_momentum(kk, sr=None, obv=None, volx=None, z=0.0, regime=''):
    """P13: bos minta tau KONTEKS - gini nggak dia cuma nebak score.
    Klasifikasi otomatis dari data fapi realtime per sinyal:
      wick_extreme      = climax ekstrem (|z|>=2.5 / RSI6>90 / <10) -> fade
      momentum_fallback = trend kuat -> ikut momentum
      mean_reversion    = chop/range -> balik mean
      breakout          = volx>2.5 + body>60% -> breakout (hati-hati false break)
      kering            = volx<1.0 -> tidak ada aliran, skip
    """
    c=[r[4] for r in kk]; o=[r[1] for r in kk]
    rng=kk[-1][2]-kk[-1][3]
    body=abs(c[-1]-o[-1])/rng if rng>0 else 0
    try:
        _, r6 = rsi6_series(c)
    except Exception:
        r6 = None
    if volx is not None and volx < 1.0:
        cls='kering'
    elif abs(z) >= 2.5 or (r6 is not None and (r6 > 90 or r6 < 10)):
        cls='wick_extreme'
    elif volx is not None and volx > 2.5 and body > 0.6:
        cls='breakout'
    elif regime and 'TREND' in str(regime).upper():
        cls='momentum_fallback'
    else:
        cls='mean_reversion'
    return cls, (round(r6,1) if r6 is not None else None)


def enrich_briefing(brief, kk, rs=None):
    """P13: suntik vision pack ke briefing bos - chart RSI6, momentum class, bar detail.
    Return dict briefing BARU (jangan mutasi asli)."""
    import copy
    b=copy.deepcopy(brief)
    c=[r[4] for r in kk]
    try:
        r6sp, r6 = rsi6_series(c)
    except Exception:
        r6sp, r6 = None, None
    score=b.get('score',{}) if isinstance(b.get('score'),dict) else {}
    volx=score.get('vol_x'); z=score.get('z',0.0)
    try:
        cls,r6v = classify_momentum(kk, volx=volx, z=z, regime=b.get('regime',''))
    except Exception:
        cls,r6v = 'mean_reversion', r6
    return b
