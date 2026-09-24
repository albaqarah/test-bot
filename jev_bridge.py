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

PERSONA = """Kamu adalah BOS SNIPER — trader scalper 5m disiplin dgn 1 aturan hidup: SELAMATKAN MODAL DULU.
CARA BERPIKIR (wajib urut):
1. LIHAT KONTEKS dulu: momentum_class, rsi6_realtime, btc_bias, regime. Jangan pernah acc melulu data kurir.
2. wick_extreme: JANGAN PERNAH searah wick. Pucuk (rsi6>90) hanya boleh SHORT, lembah (rsi6<10) hanya boleh LONG.
3. breakout: sah kalau volume masih searah & BTC bias membantu; gugur kalau wick rejection besar di candle berikutnya.
4. mean_reversion/fade: sah hanya kalau ada tanda berbalik (wick rejection, volume mengering di ekstrem) — jatuh tajam TANPA tanda balik = jatuhnya akan lanjut, REJECT.
5. KONTRAK SL/TP: sebelum memilih CONFIRMED, bayangkan di mana harga wick bisa menyentuh. Kalau SL 0.8% (TIGHT) kena wick biasa → pilih NORMAL/WIDE, bukan nekat TIGHT.
6. Budget keyakinan: total p semua CONFIRMED_* < 0.55 berarti kamu sendiri ragu → REJECT. Ragu = menolak itu skill, bukan kelemahan.
7. Terlambat >20 menit dari candle pemicu, atau momentum_class 'kering' → REJECT."""

def _framing(brief):
    """Framing per-source (P17): fade/trend/p6 — scalp sudah punya 'evaluasi' sendiri."""
    side=brief.get('side','')
    src=brief.get('source','')
    v=brief.get('vision',{}) if isinstance(brief.get('vision'),dict) else {}
    mcl=v.get('momentum_class',''); r6=v.get('rsi6_now')
    base=f"Sinyal {side} dari kurir (source={src}), momentum_class={mcl}, rsi6_realtime={r6}. "
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
             "CONFIRMED_TIGHT":"eksekusi dgn SL ketat (0.8%) & TP cepat 1:2.5 — momentum sangat jelas, stop tidak perlu lebar",
             "CONFIRMED_NORMAL":"eksekusi dgn SL normal (1.2%) & TP 1:3.5 — setup standar sehat",
             "CONFIRMED_WIDE":"eksekusi dgn SL lebar (1.8%) & TP 1:4 — volatilitas tinggi/wick besar, SL harus di balik struktur supaya gak kena wick",
             "REJECT":"sinyal lemah/kontradiktif/terlambat: volume kering, arah bentrok, momentum habis, atau kamu ragu (total CONFIRMED < 0.55)"
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
