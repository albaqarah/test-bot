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

def call_jev(brief, symbol=''):
    """brief = dict briefing (dari dewa_skill.build_briefing). Return {decision,confidence,reason,key_factor}."""
    if not KEY:
        raise RuntimeError('JEV_API_KEY kosong')
    state=json.dumps(brief, ensure_ascii=False, separators=(',',':'))
    p={"model":MODEL,
       "state":state,
       "questions":{
         "decision":{"type":"choice",
           "instructions":brief.get('evaluasi','Putuskan apakah sinyal ini layak dieksekusi (CONFIRMED) atau ditolak (REJECT). Pilih SATU. Untuk CONFIRMED, pilih varian eksekusi: pikirkan di mana SL aman di balik struktur (tidak kena wick) dan TP yang realistis di swing berikutnya.'),
           "criteria":{
             "CONFIRMED_TIGHT":"eksekusi dgn SL ketat (0.8%) & TP cepat 1:2.5 — momentum sangat jelas, stop tidak perlu lebar",
             "CONFIRMED_NORMAL":"eksekusi dgn SL normal (1.2%) & TP 1:3.5 — setup standar sehat",
             "CONFIRMED_WIDE":"eksekusi dgn SL lebar (1.8%) & TP 1:4 — volatilitas tinggi/wick besar, SL harus di balik struktur supaya gak kena wick",
             "REJECT":"sinyal lemah/kontradiktif/terlambat: volume kering, arah bentrok, atau momentum habis"
           }}}
    }
    resp=_req(p)
    a=resp.get('answers',{}).get('decision',{})
    choice=str(a.get('choice','')).upper()
    probs=a.get('probabilities',{})
    # confidence = peluang pilihan yang menang (0..1) — lebih informatif daripada self-report confidence
    conf=float(probs.get(choice, a.get('confidence',0)))
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
