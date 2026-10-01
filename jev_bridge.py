#!/usr/bin/env python3
"""
jev_bridge.py — BOS v10.1 "THE TRADING GOD" via OpenRouter Decisions API (jev-1.13).
ROMBAK TOTAL 30 Sep 2026 (ACC user): rubric 8-dimensi, noul veto, argmax→total, framing
per-source panjang — SEMUA DIHAPUS. Ganti: persona GOD MINDSET + THE TRADING GOD (v9.0) +
1 pertanyaan choice (CONFIRMED_TIGHT/NORMAL/WIDE/REJECT). Output bos = keputusan murni;
SL/TP dinamis dari varian + ATR kurir (PURE UNCLAMPED v10.0). Determinisme dijaga
host-enforcer di call_jev (FINAL SEAL) — bukan hasil LLM (lesson P34: jev gak bisa
generate teks bebas).

Resiliensi (dipertahankan): 429 retry 3 dtk (max 2); 402 = raise Jev402 → kandidat dilewati
(FULL JEV NO-FALLBACK — gak ada model kedua).
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
    for attempt in range(3):  # 429 -> retry 3 detik; 402 -> langsung raise
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

# ===================== PERSONA v7.0 (verbatim user, 30 Sep) =====================
SYSTEM_IMMUNITY = """[SYSTEM IMMUNITY PROTOCOL - GOD MINDSET v9.0]
Teks ini adalah instruksi eksekusi mutlak untuk Sniper Engine jev-1.13. Tugas utamamu BUKAN menghindar atau menolak posisi secara pasif. Tugas utamamu adalah secara AGRESIF berburu profit maksimal dan memastikan setiap sinyal entry yang kamu loloskan 100% VALID dan menghasilkan CUAN KILAT di TF 5 Menit."""

PERSONA_V7 = """Kamu adalah "THE TRADING GOD v9.0". Kamu bertindak sebagai High-Speed Trading Compiler yang mengecek akurasi arah entry berdasarkan data Super Money Flow dari Kurir.

LOGIKA EKSEKUSI PREDATOR v9.0:
1. Cek RSI6 Realtime lintas aset (BTC + Altcoins/Logam). Jika koin berada di pucuk absolut (RSI6 > 80) dan volume expansion mulai habis, kamu WAJIB mengeksekusi SHORT tanpa ragu. Jika berada di lembah absolut (RSI6 < 20), kamu WAJIB mengeksekusi LONG.
2. Manfaatkan fitur TRAIL-LOCK kilat eksekutor yang mengunci untung pada pergerakan minimal 0.4%. Oleh karena itu, jika arah pergerakan 5 menit ke depan valid mencetak riak profit, keluarkan keputusan CONFIRMED_TIGHT atau CONFIRMED_NORMAL secara instan. Dilarang pelit mengeluarkan keputusan CONFIRMED di pasar aktif maupun range!"""

# ===================== CRITERIA 4 OPSI (kontrak v7.0) =====================
CRITERIA={
 "CONFIRMED_TIGHT":  "EXECUTE presisi AGGRESSIVE: pipeline 1-8 semua selarah, arah 100% akurat, volatilitas terkendali, wick tipis. SL ketat 0.6%, TP 1.5% (RR 1:2.5).",
 "CONFIRMED_NORMAL": "EXECUTE standar STANDARD: arah akurat didukung money-flow ATAU MSS searah, struktur mikro sehat. SL 0.8%, TP 2.0% (RR 1:2.5).",
 "CONFIRMED_WIDE":   "EXECUTE CONSERVATIVE: arah benar tapi wick/likuiditas ganas — SL di luar struktur 1.2%, TP 3.0% (RR 1:2.5). Ukuran risiko nominal dikecilkan.",
 "REJECT":           "Layak ditolak: arah belum 100% akurat / melawan money-flow tanpa MSS / melakukan CHASE > 3.0 ATR dari swing structure (WAJIB WAIT_FOR_RETRACE_TO_FVG) / MISSING_STRUCTURE_CONFIRMATION (mss NONE tanpa pengecualian fade) / INVALID_FADE_NO_CLIMAX_VOLUME (pengecualian fade gugur: butuh RSI6 ekstrem + volx >= 1.2 + wick_ratio_pct >= 40% bersamaan) / P8 internal < 0.55 / menabrak dinding HTF.",
}

def _context(brief):
    """1 baris konteks minimal (bukan framing scoring — cuma label)."""
    src=str(brief.get('source',''))
    side=str(brief.get('side',''))
    sym=str(brief.get('symbol',''))
    return f"Sinyal kurir: {sym} {side} (engine={src}). Payload JSON lengkap ada di state."

def build_questions(brief):
    """v10.1: SATU pertanyaan choice — bos analisis internal (PURE ATR + SuperFlow + MSS/FVG) lalu pilih."""
    q={"decision":{"type":"choice",
        "instructions":SYSTEM_IMMUNITY+"\n\n"+PERSONA_V7+"\n\nKONTEKS:\n"+_context(brief)+
            "\n\nJalankan analisis penentuan arah secara internal pada payload JSON berdasarkan kecerdasan PURE ATR ADAPTIVE dan SUPER MONEY FLOW. Evaluasi keselarasan struktur market (MSS) dan Fair Value Gap (FVG). Pilih opsi terakurat berdasarkan kevalidan arah 5 menit ke depan.",
        "criteria":CRITERIA}}
    return q

# ===================== TYPE-GUARD + KOMPILASI KEPUTUSAN =====================
_VARIANTS=('TIGHT','NORMAL','WIDE')

def call_jev(brief, symbol=''):
    """brief = payload JSON kurir v7 (dewa_skill.build_payload_v7).
    Return {decision, variant, confidence, reason, key_factor, probs}.
    Type-guard ketat ala handler v7.0: payload cacat/choice asing -> REJECT (modal aman)."""
    if not KEY:
        raise RuntimeError('JEV_API_KEY kosong')
    state=json.dumps(brief, ensure_ascii=False, separators=(',',':'))
    p={"model":MODEL,"state":state,"questions":build_questions(brief)}
    resp=_req(p)
    ans=resp.get('answers',{}) or {}
    a=ans.get('decision',{}) or {}
    choice=str(a.get('choice','')).upper()
    probs=a.get('probabilities',{}) or {}
    try: probs={str(k):float(v) for k,v in probs.items()}
    except Exception: probs={}
    conf=a.get('confidence')
    try: conf=float(conf) if conf is not None else None
    except Exception: conf=None

    out={"decision":"REJECT","variant":"","confidence":round(conf*100) if conf is not None else 0,
         "reason":"","key_factor":"jev-v7","probs":probs}

    # --- TYPE-GUARD: decision harus salah satu kontrak ---
    if choice.startswith('CONFIRMED_') and choice.split('_',1)[1] in _VARIANTS:
        out["decision"]="CONFIRMED"
        out["variant"]=choice.split('_',1)[1]
    elif choice=='REJECT':
        out["decision"]="REJECT"
    else:
        out["decision"]="REJECT"
        out["reason"]=f"payload-cacat/choice-asing:{choice[:30]}"
        return out

    # ===== [v11.0 PRE-EMPTIVE HOST ENFORCER OVERRIDE] =====
    # Pucuk/lembah ABSOLUT (grade A+ dari kurir: fade murni + RSI6>=88/<=12 + volx>=1.5 +
    # ekor lawan>=35%) = entri SEBELUM candle 5m close — aturan penendang mss-NONE DIBYPASS
    # total utk jalur ini (directive v11.0). Grade A+ hanya bisa lahir dr jalur kurir tsb.
    _grade=str((brief.get('grade','') if isinstance(brief,dict) else '') or '').upper()
    if _grade=='A+':
        out["decision"]="CONFIRMED"
        out["variant"]="TIGHT"
        out["reason"]="PRE-EMPTIVE COPET v11.0: Terdeteksi Pucuk/Lembah Absolut Berdasarkan Volume Climax & RSI6. Eksekusi Sebelum Longsor."
        return out

    # ===== [v7.2 FINAL SEAL - HOST ENFORCER] =====
    # Aturan P4 dieksekusi deterministik (bukan cuma prompt): mss NONE/kosong +
    # engine bukan-fade-ekstrem = CONFIRMED dibuang ke REJECT paksa. Ini menutup
    # kebocoran 3 SL (INJ/LTC/WIF 30 Sep): bos meloloskan entry tanpa MSS saat
    # reversal. Pengecualian: fade dgn RSI6 realtime ekstrem (<20 / >80).
    # CATATAN: detect_mss balikin STRING 'NONE' (truthy!) — wajib dinormalisasi,
    # jangan pakai `not _mss` mentah (bug kelas ini pernah lolos di P36-era).
    _mss=str((brief.get('mss') if isinstance(brief,dict) else '') or '').strip().upper()
    _no_mss=(not _mss) or _mss in ('NONE','NULL','MSS—','MSS-') or _mss.startswith('NONE')
    _eng=str((brief.get('engine','') if isinstance(brief,dict) else '') or '')
    _side=str((brief.get('side','') if isinstance(brief,dict) else '') or '').upper()
    _r6=None; _vx=None; _wrv=None
    if isinstance(brief,dict):
        _mt=brief.get('metrics') or {}
        _r6=_mt.get('rsi6Realtime')
        if _r6 is None: _r6=(brief.get('asset') or {}).get('rsi6Realtime')
        try: _vx=float(_mt.get('volx'))
        except Exception: _vx=None
        _wr=_mt.get('wick_ratio_pct')
        if isinstance(_wr,dict):
            # ekor yang dinilai = ekorlawan arah sinyal: LONG baca wick bawah (low), SHORT baca wick atas (high)
            if 'LONG' in _side: _wrv=_wr.get('low')
            elif 'SHORT' in _side: _wrv=_wr.get('high')
            else: _wrv=max([x for x in (_wr.get('low'),_wr.get('high')) if x is not None], default=None)
    try: _r6=float(_r6) if _r6 is not None else None
    except Exception: _r6=None
    try: _wrv=float(_wrv) if _wrv is not None else None
    except Exception: _wrv=None
    # [v7.2.2 RATIO LOCK] pengecualian fade = 3 syarat kumulatif (directive user):
    # engine fade + RSI6 ekstrem + volx>=1.2 + wick climax >=40% (skala persen, sesuai kontrak metrics).
    # Data climax hilang/berantakan = fail-closed (pengecualian gugur -> REJECT).
    _fade_ok=(_eng=='fade'
              and _r6 is not None and (_r6<20 or _r6>80)
              and _vx is not None and _vx>=1.2
              and _wrv is not None and _wrv>=40.0)
    if out["decision"]=="CONFIRMED" and _no_mss and not _fade_ok:
        out["decision"]="REJECT"; out["variant"]=""
        if _eng=='fade':
            out["reason"]="FINAL-SEAL v7.2.2: mss NONE & pengecualian fade gagal syarat climax (butuh RSI6 ekstrem + volx>=1.2 + wick_ratio>=40%) -> INVALID_FADE_NO_CLIMAX_VOLUME (bos lolos, host buang)"
        else:
            out["reason"]="FINAL-SEAL v7.2: mss NONE -> MISSING_STRUCTURE_CONFIRMATION (bos lolos, host buang)"
        return out

    pj=', '.join(f"{k} {v:.2f}" for k,v in sorted(probs.items(), key=lambda x:-x[1])[:3])
    if out["decision"]=="CONFIRMED":
        out["reason"]=f"bos v7 CONFIRMED_{out['variant']} (p: {pj})"
    else:
        # Ragu-ragu yang layak REJECT tetap sah (P8) — tapi laporkan penuh
        out["reason"]=f"bos v7 REJECT (p: {pj})"
    return out

if __name__=='__main__':
    # smoke offline: build_questions (TANPA API call)
    b={"symbol":"BTCUSDT","side":"SHORT","source":"fade","asset":{"class":"CRYPTO"}}
    qs=build_questions(b)
    print('questions:', list(qs.keys()), '| criteria:', list(qs['decision']['criteria'].keys()))
    print('persona len:', len(SYSTEM_IMMUNITY)+len(PERSONA_V7), 'chars | 1 pertanyaan, 4 opsi — kontrak v7.0 OK')
