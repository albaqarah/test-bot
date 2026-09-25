#!/usr/bin/env python3
"""
jev_bridge.py — Adapter bos LLM ke TypeSafe jev-1.13 via OpenRouter Decisions API.
Skema (dicek langsung ke server, 23 Sep 2026):
  POST {base}  {model, state, questions:{name:{type:'choice'|'score'|'noul',
                instructions, criteria:{NAMA:'desc'}}}}
  choice  -> criteria keys = pilihan (probabilities per pilihan + confidence 0..1)
  Response: {answers:{name:{type, choice, probabilities, confidence}}, usage:{cost}}
Output adapter = bentuk sama dgn llm_call lightvela: {decision, confidence, reason, key_factor}
"""
import json, os, urllib.request, time

BASE=os.environ.get('JEV_BASE_URL','https://openrouter.ai/api/alpha/decisions')
KEY=os.environ.get('JEV_API_KEY','')
MODEL=os.environ.get('JEV_MODEL','typesafe/jev-1.13')
TIMEOUT=float(os.environ.get('JEV_TIMEOUT','12'))

def _req(payload):
    H={'Authorization':f'Bearer {KEY}','Content-Type':'application/json',
       'HTTP-Referer':'https://github.com/albaqarah/test-bot','X-Title':'dewa-bot'}
    req=urllib.request.Request(BASE, data=json.dumps(payload).encode(), headers=H, method='POST')
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)

PERSONA = """Kamu adalah TYPESAFE SNIPER v3.5 — Money-Flow & SMC Engine scalper TF 5m.
CORE DIRECTIVE: hasilkan profit konsisten. Bukan penolak pasif — AKTIF cari entry dgn probabilitas
tertinggi via korelasi BTC-BTC.D (crypto) / DXY (TradFi metal) + konfirmasi mikro SMC (MSS & FVG).
SELAMATKAN MODAL: trade yang gak layak tetap di-REJECT — tapi yang layak HARUS dieksekusi.

PIPELINE WAJIB (urut):
1. DETEKSI ASET: assetClass CRYPTO (inkl PAXG) -> baca moneyFlow matriks BTC+btcDominance.
   TRADFI_METAL (XAU/XAG/XPT) -> abaikan BTC.D, baca dxyBias (BULLISH dolar = SHORT logam; BEARISH = LONG logam; SIDEWAYS = struktur internal saja).
2. MONEY-FLOW MATRIX (crypto): BULLISH+RISING=BTC saja | BULLISH+FALLING=LONG alts terbaik |
   BEARISH+RISING=SHORT alts | BEARISH+FALLING=short-bias total | SIDEWAYS+FALLING=LONG alts rotasi.
   Sinyal yang MELAWAN arah money-flow butuh bukti mikro kuat utk CONFIRMED (MSS searah + volume).
3. MSS (Market Structure Shift): reversal sah HANYA jika close-candle menembus swing high/low terakhir
   (mss=MSS_BULLISH/MSS_BEARISH). Satu candle besar TANPA close-break = bukan reversal, jangan asumsi balik arah.
4. FVG (Fair Value Gap): JANGAN PERNAH ngejar harga yang sudah terbang/longsor dgn SL ketat. Setup
   IDEAL: MSS terkonfirmasi -> retrace masuk fvgRange -> entry zona itu (kalau harga BELUM retrace,
   boleh CONFIRMED dgn WIDE/atau REJECT-await-retrace — pilih yg probabilitasnya lebih tinggi).
   fvgStatus=NONE bukan larangan — cuma kurangi bobot keyakinan (harga pasar langsung boleh, kalau
   momentum & money-flow kuat).
5. WICK EXTREME & LIQUIDITY: rsi6Realtime>90 = hanya berpikir SHORT (mirror <10 = LONG) — TAPI jika
   makro + MSS searah breakout sah, wick ekstrem setelah liquidity sweep = manipulasi: jangan counter-trend
   mentah-mentah; kalau makro kuat boleh CONFIRMED (prefer WIDE). Entry searah wick TANPA MSS & tanpa
   konfirmasi momentum = REJECT.
6. KONTRAK SL/TP (Dynamic Risk): SL 0.8% (TIGHT) dilarang saat volatilitas/wick besar. Hitung jarak aman
   dari ujung wick terdekat & struktur MSS; pilih WIDE dgn TP 1:4 kalau wick kejam. Lebar SL tetap aman krn
   notional kecil — yang dijaga adalah RISIKO NOMINAL, bukan persentase.
7. CONFIDENCE BUDGET: skor = keselarasan RSI(20%)+Volume(30%)+Matrix makro/MSS(50%).
   Total p semua CONFIRMED_* < 0.55 = kamu belum yakin -> REJECT (ragu itu skill, bukan kelemahan).
8. momentum_class 'kering' (volx<1.2) atau sinyal telat >20 menit -> REJECT."""

def _framing(brief):
    """Framing per-source (P17): fade/trend/p6 — scalp sudah punya 'evaluasi' sendiri."""
    side=brief.get('side','')
    src=brief.get('source','')
    v=brief.get('vision',{}) if isinstance(brief.get('vision'),dict) else {}
    mcl=v.get('momentum_class',''); r6=v.get('rsi6_now')
    base=f"Sinyal {side} dari kurir (source={src}), momentum_class={mcl}, rsi6_realtime={r6}. "
    _mf=brief.get('moneyFlow') or brief.get('tradfiMoneyFlow') or ''
    if _mf: base+=f" MONEY-FLOW AKTIF: {_mf}. "
    if src=='fade':
        return base+"FADE: ini taruhan BERBALIK arah. Wajib ada bukti berbalik: wick rejection di ekstrem, volume mengering, stoch_rsi belok. Jatuh/naik tajam TANPA tanda balik akan LANJUT — itu REJECT, bukan diskon."
    if src=='trend':
        return base+"TREND-PULLBACK: taruhan tren LANJUT setelah koreksi kecil. Sah kalau pullback dangkal (ema25 tahan), volume turun saat pullback & naik lagi searah tren. Pullback dalam + volume lawan = tren patah → REJECT."
    if src=='p6':
        return base+"FADE-LOOSE (P6): fade dengan syarat longgar. Karena longgar, kamu harus LEBIH galak: tanpa bukti berbalik yang jelas → REJECT. Grade B fade bukan izin nekat."
    return base+"Nilai apakah setup ini benar2 layak dieksekusi sekarang. Ragu → REJECT."

def call_jev(brief, symbol=''):
    """brief = dict briefing (dari dewa_skill.build_briefing). Return {decision,confidence,reason,key_factor}."""
    if not KEY:
        raise RuntimeError('JEV_API_KEY kosong')
    state=json.dumps(brief, ensure_ascii=False, separators=(',',':'))
    framing=brief.get('evaluasi') or _framing(brief)
    p={"model":MODEL,
       "state":state,
       "questions":{
         "decision":{"type":"choice",
           "instructions":PERSONA+"\n\nFRAMING SINYAL INI:\n"+framing,
           "criteria":{
             "CONFIRMED_TIGHT":"EXECUTE presisi: setup sempurna — searah money-flow + MSS searah + volume aligned, wick kecil (SL 0.8%, TP 1:2.5)",
             "CONFIRMED_NORMAL":"EXECUTE standar sehat: searah money-flow ATAU MSS searah, struktur mikro mendukung (SL 1.2%, TP 1:3.5)",
             "CONFIRMED_WIDE":"EXECUTE dgn risiko wick: arah benar tapi wick/likuiditas ganas — SL di balik struktur (1.8%, TP 1:4). Pilihan UTAMA utk reversal pasca wick-extreme",
             "REJECT":"LAYAK DITOLAK: lawan money-flow tanpa MSS, momentum kering, telat, atau total CONFIRMED < 0.55. Kalau arah benar tapi harga belum retrace ke FVG, pakai REJECT — kurir bakal nanya lagi saat retrace"
           }}}}
    resp=_req(p)
    a=resp.get('answers',{}).get('decision',{})
    choice=str(a.get('choice','')).upper()
    probs=a.get('probabilities',{})
    # P17: conf = p(TOTAL semua CONFIRMED_*) — apple-to-apples dgn era 2-kriteria (dulu 0.72-0.86).
    # Dulu pakai p pilihan menang → prob pecah 4 varian bikin conf ACC 0.36 (padahal total 0.77) →
    # sinyal ragu-ragu lolos gerbang = akar lose 25 Sep.
    conf=float(sum(float(v) for k,v in probs.items() if str(k).upper().startswith('CONFIRMED')) or probs.get(choice, a.get('confidence',0)))
    # reason generatif dari data (jev gak nulis teks): pakai probabilitas per pilihan
    pj=', '.join(f"{k} {v:.2f}" for k,v in sorted(probs.items(), key=lambda x:-x[1])[:3])
    reason=f"jev {choice.lower()} (p: {pj})" if pj else f"jev {choice.lower()}"
    if choice.startswith('CONFIRMED'):
        variant=choice.split('_',1)[1] if '_' in choice else 'NORMAL'
        return {"decision":"CONFIRMED","confidence":round(conf*100),
                "reason":reason,"key_factor":'jev',"variant":variant}
    if choice=='REJECT':
        return {"decision":"REJECT","confidence":round(conf*100),
                "reason":reason,"key_factor":'jev'}
    return {"decision":"REJECT","confidence":round(conf*100),
            "reason":f"jev_unknown_choice:{choice[:30]}","key_factor":'jev'}

if __name__=='__main__':
    # smoke: python3 jev_bridge.py
    b={"symbol":"BTCUSDT","grade":"A","side":"SHORT","score":{"z":2.15,"rsi":84.1},
       "regime":"RANGE","funding":0.0001,"vol_x":1.7,"wick_rejection":True}
    print(json.dumps(call_jev(b), ensure_ascii=False))
