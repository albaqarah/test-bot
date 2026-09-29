#!/usr/bin/env python3
"""
jev_bridge.py — Adapter bos LLM ke TypeSafe jev-1.13 via OpenRouter Decisions API.
P32 (28 Sep 2026): MULTI-QUESTION 1 request (1 choice + 8 score + 2 noul) + WICK-HUNTER persona.
Skema: POST {base} {model, state, questions:{name:{type:'choice'|'score'|'noul', instructions, criteria}}}
  choice -> {choice, probabilities, confidence}; score -> nilai 0-4; noul -> teks.
Resiliensi (koreksi user 28 Sep): 429 = retry 3 detik (max 2); 402 = raise Jev402
-> FULL JEV NO-FALLBACK (P35): error sesaat = kandidat dilewati, diulang iterasi berikutnya.
"""
import json, os, urllib.request, urllib.error, time

BASE=os.environ.get('JEV_BASE_URL','https://openrouter.ai/api/alpha/decisions')
KEY=os.environ.get('JEV_API_KEY','')
MODEL=os.environ.get('JEV_MODEL','typesafe/jev-1.13')
TIMEOUT=float(os.environ.get('JEV_TIMEOUT','12'))

class Jev402(Exception):
    """Quota/kredit habis — JANGAN retry, langsung ganti provider."""
    pass

def _req(payload):
    H={'Authorization':f'Bearer {KEY}','Content-Type':'application/json',
       'HTTP-Referer':'https://github.com/albaqarah/test-bot','X-Title':'dewa-bot'}
    last=None
    for attempt in range(3):  # 429 -> retry 3 detik (koreksi user); 402 -> langsung raise
        try:
            req=urllib.request.Request(BASE, data=json.dumps(payload).encode(), headers=H, method='POST')
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==402:
                raise Jev402('HTTP 402 Payment Required — jev butuh topup')
            if e.code==429 and attempt<2:
                time.sleep(3); last=f'HTTP 429 (retry {attempt+1})'; continue
            raise
    raise RuntimeError(last or 'jev_req_failed')

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
5. WICK EXTREME: JANGAN counter wick buta (bekas kepala SL). Fade wick butuh makro searah (BTC.D/DXY) — TAPI jika
   makro + MSS searah breakout sah, wick ekstrem setelah liquidity sweep = manipulasi: jangan counter-trend
   mentah-mentah; kalau makro kuat boleh CONFIRMED (prefer WIDE). Entry searah wick TANPA MSS & tanpa
   konfirmasi momentum = REJECT.
6. KONTRAK SL/TP (Dynamic Risk): SL 0.8% (TIGHT) dilarang saat volatilitas/wick besar. Hitung jarak aman
   dari ujung wick terdekat & struktur MSS; pilih WIDE dgn TP 1:4 kalau wick kejam. Lebar SL tetap aman krn
   notional kecil — yang dijaga adalah RISIKO NOMINAL, bukan persentase. Referensi: slSuggest.sl_pct_suggest
   dari kurir (ATR14x1.5) — pakai sebagai patokan lebar SL, override varian kalau wick lebih kejam.
7. CONFIDENCE BUDGET: skor = keselarasan RSI6(20%)+Volume(30%)+Matrix makro/MSS(50%).
   Total p semua CONFIRMED_* < 0.55 = kamu belum yakin -> REJECT (ragu itu skill, bukan kelemahan).
8. momentum_class 'kering' (volx<1.2) atau sinyal telat >20 menit -> REJECT.
9. WICK-HUNTER (data kurir 'wickHint' — entry EARLY pucuk/lembah, prioritas bos):
   - wickHint.dir SEARAH sinyal + strength >= 70 + climax=true -> sinyal MENGUAT: boleh CONFIRMED
     (prefer TIGHT/NORMAL — SL ketat di balik wick; ini entry pucuk/lembah paling awal).
   - searah + strength 50-69 -> butuh konfirmasi ke-2 (MSS/FVG searah) baru boleh CONFIRMED.
   - wickHint.dir LAWAN sinyal + strength >= 70 -> WAJIB REJECT (jangan ayunkan pisau ke wick lawan).
   - wickHint.dir=NONE atau strength < 50 -> abaikan, nilai pakai pipeline 1-8.
   - divergence (market.divergence): bear_div melawan LONG / bull_div melawan SHORT = turunkan keyakinan.
10. MARKET SNAPSHOT (data kurir 'market'): vwap_z (harga vs VWAP): z <= -2 = DISKON (bagus utk LONG,
    buruk utk SHORT entry); z >= +2 = PREMIUM (bagus utk SHORT, bahaya utk LONG ngekor). squeeze_on=true +
    breakout vol tinggi = setup momentum terbaik; regime_strength CHOP = percayakan ke fade/rejection,
    TREND = follow-through. mtf.score: 3/3 penuh = aman; 1/3 = melawan TF besar -> butuh bukti ekstra.
    book_imb searah + ask/bid wall jadi referensi SL (di balik dinding).
DISIPLIN URUTAN: proses P1 sampai P10 SELALU berurutan — dilarang melompati langkah
atau memilih sebelum semua langkah lewat."""

# P32 RUBRIC: 8 dimensi 0-4. timing_freshness & liquidity_risk bobot x2.
# P34 FIX (29 Sep): criteria score HARUS 5 item (0,1,2,3,4) — dulu 3 item bikin jev cuma bisa jawab
# 0-2 (array = pilihan terbatas), setup sempurna ke-gas di gate 50. Tervalidasi live: 3.95/1.62/0.74.
RUBRIC=[
 ("rs_quality",  "KUALITAS SETUP", "Kualitas setup keseluruhan setelah pipeline 1-10",
  ["0 = Sinyal sampah: melawan hampir semua lapisan",
   "1 = Lemah: 1-2 bukti pendukung saja",
   "2 = Medioker: bukti campur, tidak yakin",
   "3 = Bagus: mayoritas lapisan searah",
   "4 = Sempurna: makro+MSS+volume+lokasi selaras penuh"]),
 ("rs_timing",   "TIMING & FRESHNESS (bobot 2x)", "Segar tidaknya entry sekarang (pucuk/lembah)",
  ["0 = Telat: kejar harga terbang (vwap_z ekstrem lawan)",
   "1 = Ketinggalan: gerakan utama lewat, risiko retrace dalam",
   "2 = Netral: harga di tengah jalan",
   "3 = Cepat: baru mulai berbalik, masih bisa nyusul",
   "4 = Lemparan awal di pucuk/lembah: wickHint searah strength tinggi ATAU vwap_z diskon/premium + climax"]),
 ("rs_liquidity","LIKUIDITAS & RISIKO WICK (bobot 2x)", "Risiko kena wick/likuidasi dini",
  ["0 = SL pasti kena wick: deket wall lawan / ATR ganas / SL di dlm range",
   "1 = Wick kejam: jarak SL sempit dibanding noise",
   "2 = Wick biasa: SL standar aman",
   "3 = Aman: SL ada ruang, ATR moderat",
   "4 = Sangat aman: SL di balik struktur+wall searah, ATR tenang, book_imb searah"]),
 ("rs_trend",    "TREND ALIGNMENT MTF", "Keselarasan 5m/15m/1h + money-flow",
  ["0 = Melawan money-flow DAN mtf.score 0-1/3",
   "1 = Lawan mayoritas TF",
   "2 = Campur: 2/3 ATAU lawan satu lapisan saja",
   "3 = Mayoritas searah",
   "4 = mtf 3/3 + money-flow searah"]),
 ("rs_rr",       "RR & LOKASI", "Kualitas risk-reward dari lokasi entry ini",
  ["0 = RR efektif buruk: entry di lokasi jelek (tengah range/kejar)",
   "1 = Lokasi bawah standar",
   "2 = RR standar regime",
   "3 = RR bagus: dekat zona kunci",
   "4 = Entry tepat di zona (FVG/wick/EMA) dgn TP multi-R realistis"]),
 ("rs_crowd",    "POSISI CROWD", "Seberapa crowded posisi lawan/serupa",
  ["0 = Crowded ekstrem lawan arah: funding ekstrem + OI meledak lawan",
   "1 = Crowd condong lawan",
   "2 = Netral (funding/OI tenang)",
   "3 = Crowd mulai kalah arah",
   "4 = Crowd kalah arah: funding/OI mendukung gerakan ini"]),
 ("rs_vol",      "VOLATILITY FIT", "Cocok tidaknya volatilitas dgn gaya scalp 5m",
  ["0 = Volatilitas mati (dry_up/ADX<15) ATAU ganas gila (ATR>2.5%)",
   "1 = Vol tidak cocok utk scalp",
   "2 = Vol normal",
   "3 = Vol sehat searah",
   "4 = Squeeze_on baru pecah ATAU vol sehat searah penuh"]),
 ("rs_session",  "SESSION FIT", "Kualitas sesi WIB saat ini",
  ["0 = OFFHOURS/weekend TradFi logam, volume kopong",
   "1 = Sisi sepi",
   "2 = Sesi netral",
   "3 = Sesi aktif",
   "4 = LONDON/NEWYORK utk crypto/logam dgn vol sehat"]),
]

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

def build_questions(brief):
    """P32: 1 choice + 8 score + 2 noul = 11 pertanyaan dlm SATU request (biaya sama)."""
    q={"decision":{"type":"choice",
        "instructions":PERSONA+"\n\nFRAMING SINYAL INI:\n"+_framing(brief),
        "criteria":{
          "CONFIRMED_TIGHT":"EXECUTE presisi: setup sempurna — searah money-flow + MSS searah + volume aligned, wick kecil (SL 0.8%, TP 1:2.5)",
          "CONFIRMED_NORMAL":"EXECUTE standar sehat: searah money-flow ATAU MSS searah, struktur mikro mendukung (SL 1.2%, TP 1:3.5)",
          "CONFIRMED_WIDE":"EXECUTE dgn risiko wick: arah benar tapi wick/likuiditas ganas — SL di balik struktur (1.8%, TP 1:4). Pilihan UTAMA utk reversal pasca wick-extreme",
          "REJECT":"LAYAK DITOLAK: lawan money-flow tanpa MSS, momentum kering, telat, atau total CONFIRMED < 0.55. Kalau arah benar tapi harga belum retrace ke FVG, pakai REJECT — kurir bakal nanya lagi saat retrace"
        }}}
    for name,label,inst,crit in RUBRIC:
        # P34: criteria = 5 item eksplisit (0-4). Array = pilihan terbatas: index item = nilai score.
        q[name]={"type":"score","instructions":f"{label} — {inst}. Pilih SATU angka 0-4 dari kriteria.",
                 "criteria":crit}
    # P34: noul = numerik 0-1 (tanpa teks — jev gak bisa generate kalimat). Dijadikan skor risiko:
    # tinggi = banyak cara trade ini gugur / bias gampang kebalik -> dipakai sbg veto lembut di rubric_total.
    q["noul_invalidate"]={"type":"noul","instructions":"Seberapa besar RISIKO trade ini GUGUR (invalidasi)? 0=tidak ada, 1=hampir pasti gugur."}
    q["noul_flip"]={"type":"noul","instructions":"Seberapa mudah bias ini KEBALIK oleh sinyal baru? 0=sangat stabil, 1=sangat rapuh."}
    return q

def rubric_total(answers):
    """Total rubric 0-100 (timing & liquidity x2). Return (total, detail) atau (None,{})."""
    tot=0.0; maxw=0.0; detail={}
    for name,label,inst,crit in RUBRIC:
        a=answers.get(name) or {}
        val=None
        for k in ('score','value','choice','confidence'):
            if isinstance(a.get(k),(int,float)): val=float(a[k]); break
            if isinstance(a.get(k),str):
                try: val=float(a[k]); break
                except Exception: pass
        if val is None: return None,{}
        val=max(0.0,min(4.0,val))
        w=2.0 if name in ('rs_timing','rs_liquidity') else 1.0
        tot+=val*w; maxw+=4.0*w
        detail[name]=round(val,1)
    if maxw<=0: return None,{}
    total=round(tot/maxw*100)
    # P34 NOUL VETO (koreksi user: noul numerik): rata2 noul >= 0.75 = risiko gugur/flip ekstrem
    # -> total dipotong 20 poin (bisa memicu KILL<50 padahal rubric bagus).
    nv=[float(a.get('noul')) for a in (answers.get('noul_invalidate'),answers.get('noul_flip'))
        if isinstance(a,dict) and isinstance(a.get('noul'),(int,float))]
    if nv:
        detail['noul_risk']=round(sum(nv)/len(nv),2)
        if sum(nv)/len(nv)>=0.75: total=max(0,total-20)
    return total, detail

def call_jev(brief, symbol=''):
    """brief = dict briefing (dari dewa_skill.build_briefing + market_snapshot.enrich_market).
    Return {decision,confidence,reason,key_factor[,variant,rubric,noul]}."""
    if not KEY:
        raise RuntimeError('JEV_API_KEY kosong')
    state=json.dumps(brief, ensure_ascii=False, separators=(',',':'))
    p={"model":MODEL,"state":state,"questions":build_questions(brief)}
    resp=_req(p)
    ans=resp.get('answers',{}) or {}
    a=ans.get('decision',{}) or {}
    choice=str(a.get('choice','')).upper()
    probs=a.get('probabilities',{}) or {}
    # P17: conf = p(TOTAL semua CONFIRMED_*) — apple-to-apples dgn era 2-kriteria.
    conf=float(sum(float(v) for k,v in probs.items() if str(k).upper().startswith('CONFIRMED')) or probs.get(choice, a.get('confidence',0)))
    # P32 RUBRIC GATE: total < 50 = KILL (paksa REJECT); 50-64 = FIX/WAIT (REJECT-await);
    # >= 65 = SHIP (keputusan choice dipertahankan).
    total, detail = rubric_total(ans)
    pj=', '.join(f"{k} {v:.2f}" for k,v in sorted(probs.items(), key=lambda x:-x[1])[:3])
    reason=f"jev {choice.lower()} (p: {pj})" if pj else f"jev {choice.lower()}"
    noul=[]
    for nk in ('noul_invalidate','noul_flip'):
        na=ans.get(nk) or {}
        tx=na.get('text') or na.get('value') or (na.get('choice') if isinstance(na.get('choice'),str) else '')
        if tx: noul.append(str(tx)[:140])
    out={"decision":None,"confidence":round(conf*100),"reason":reason,"key_factor":'jev',
         "rubric":total if total is not None else None,"noul":noul}
    if choice.startswith('CONFIRMED'):
        variant=choice.split('_',1)[1] if '_' in choice else 'NORMAL'
        out["decision"]="CONFIRMED"; out["variant"]=variant
    elif choice=='REJECT':
        out["decision"]="REJECT"
    else:
        out["decision"]="REJECT"; out["reason"]=f"jev_unknown_choice:{choice[:30]}"
    if total is not None:
        if total<50:
            out["decision"]="REJECT"
            out["reason"]+=f" [RUBRIC KILL {total}<50: {detail}]"
        elif total<65 and out["decision"]=="CONFIRMED":
            out["decision"]="REJECT"
            out["reason"]+=f" [RUBRIC WAIT {total} 50-64: {detail}]"
        else:
            out["reason"]+=f" [rubric {total}: {detail}]"
        out["rubric_detail"]=detail
    return out

if __name__=='__main__':
    # smoke offline: build_questions + rubric_total (TANPA API call)
    b={"symbol":"BTCUSDT","grade":"A","side":"SHORT","score":{"z":2.15,"rsi":84.1},
       "regime":"RANGE","funding":0.0001,"vol_x":1.7,"wick_rejection":True}
    qs=build_questions(b)
    print('questions:', list(qs.keys()))
    fake={'rs_quality':{'value':3},'rs_timing':{'value':3},'rs_liquidity':{'value':2},
          'rs_trend':{'value':4},'rs_rr':{'value':3},'rs_crowd':{'value':1},
          'rs_vol':{'value':2},'rs_session':{'value':3}}
    print('rubric_total:', rubric_total(fake)[0], '(harus 65 — bobot timing/liq 2x)')
    fake2=dict(fake); fake2['rs_timing']={'value':4}; fake2['rs_liquidity']={'value':4}
    print('rubric_total partial-max:', rubric_total(fake2)[0], '(harus 80)')
    fake3={k:{'value':4} for k,_ in [(n,0) for n,_,_,_ in RUBRIC]}
    print('rubric_total ALL-4:', rubric_total(fake3)[0], '(harus 100)')
