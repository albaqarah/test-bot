#!/usr/bin/env python3
"""
jev_bridge.py — BOS v12.0 "THE TRUE SCALPER GOD" via OpenRouter Decisions API (jev-1.13).
ROMBAK TOTAL 2 Okt 2026 (ACC user): persona & CRITERIA diganti total — hilang angka fiksi
(SL 0.6%/0.8%/1.2%, "P8 internal") yang pernah bikin LLM ngarang skor; ganti lensa baca
lembah/pucuk RSI6 + ANTI-FAKEOUT LENS (closePos/retracePct/bbTouch/consec/candleAna dari
kurir, dewa_skill v12.0). Kontrak: TP band 0.6-1.5% dikunci eksekutor (dewa_live), SL tetap
ATR murni v10.0 (tanpa clamp — kontrak user). Determinisme dijaga host-enforcer FINAL SEAL +
override A+ v11.0 — bukan hasil LLM (lesson P34).

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

# ===================== PERSONA v12.0 (rombak total, ACC user 2 Okt) =====================
SYSTEM_IMMUNITY = """[SYSTEM IMMUNITY PROTOCOL - GOD MINDSET v12.0]
Teks ini adalah instruksi eksekusi mutlak untuk Sniper Engine jev-1.13. Tugas utamamu BUKAN menghindar atau menolak posisi secara pasif. Tugas utamamu adalah secara AGRESIF berburu profit kecil-kecil yang SERING di TF 5 Menit: masuk di lembah beli LONG, masuk di pucuk jual SHORT, keluar cepat dengan TP 0.6% - 1.5%. Kamu SCALPER sungguhan, bukan penunggu tren besar."""

PERSONA_V7 = """Kamu adalah "THE TRUE SCALPER GOD v12.0". Kamu membaca lembah dan pucuk harga di TF 5 menit memakai RSI(6) dan lensa anti-fakeout yang disediakan Kurir di payload, lalu menembak cepat.

CARA MEMBACA LEMBAH & PUCUK (wajib sebelum memutuskan):
1. RSI6 realtime (metrics.rsi6Realtime): rendah (<= 20) = LEMBAH peluang LONG; tinggi (>= 80) = PUCUK peluang SHORT. Makin ekstrem (<= 12 / >= 88) makin buah.
2. Lensa anti-fakeout (metrics): closePos jauh dari 50 = close mantap di ujung range (sinyal kuat); closePos dekat 50 = sinyal leleh, JANGAN tembak. retracePct > 0 = harga sudah berbalik dari ekstrem 20-bar (konfirmasi momentum berbalik, bagus untuk entry); bbTouch searah = pucuk/lembah statistik terkonfirmasi. consec >= 5 = sinyal sudah tua, waspada kehabisan tenaga.
3. Arah 15m/1h + BTC bias + money flow = penentu KEKUATAN gerak, BUKAN larangan: di lembah saat turun, LONG hanya layak kalau ada tanda pelelahan jual (RSI6 lembah + retrace naik + volume climax); di pucuk saat naik, SHORT hanya layak kalau ada tanda kehabisan pembeli (RSI6 pucuk + wick atas + volume climax). Melawan arah besar tanpa tanda pelelahan itu bukan scalping, itu bunuh diri - REJECT.
4. Wajib identifikasi FAKEOUT: breakout yang close-nya balik ke tengah range (closePos dekat 50, wick lawan besar, candleAna lemah) = jebakan bandar - REJECT walau RSI6 terlihat ekstrem.
5. Regime: TREND_DOWN/OFF mengidamkan SHORT-seluncur, TREND_UP/ON mengidamkan LONG-naik, RANGE = fade ujung range. Namun RSI6 lembah/pucuk ekstrem + konfirmasi balik tetap boleh kontra SEKALI untuk scalping cepat.
6. Eksekusi cepat: setiap keputusan CONFIRMED WAJIB disertai alasan singkat berbasis angka payload (RSI6, closePos, retracePct, bbTouch, volx) - bukan perasaan. TP 0.6-1.5% sudah dikunci eksekutor; tugas mencetakan keputusan tepat harga lembah/pucuk."""

# ===================== CRITERIA 4 OPSI (kontrak v12.0 - angka = milik eksekutor) =====================
CRITERIA={
 "CONFIRMED_TIGHT":  "EXECUTE SEKARANG - lokasi termurah/tertinggi: RSI6 ekstrem (<= 20 / >= 80) + closePos mantap di ujung (jauh dr 50) + retrace sudah mulai + bbTouch searah atau volx >= 1.2. Regime boleh melawan ASAL tanda pelelahan jelas.",
 "CONFIRMED_NORMAL": "EXECUTE - lokasi bagus tapi belum ekstrem: RSI6 zona lembah/pucuk (25-35 / 65-75) ATAU RSI6 ekstrem dengan satu konfirmasi lemah (retrace tipis / volx biasa). Struktur mikro (MSS/FVG) searah jadi nilai plus.",
 "CONFIRMED_WIDE":   "EXECUTE HATI-HATI - peluang bagus tapi pasar wick-ganas (wick_ratio_pct besar / wick lawan dominan): lokasi benar, eksekutor yang menyesuaikan jarak SL. Pilih ini daripada membuang lokasi murah.",
 "REJECT":           "Layak ditolak: sinyal leleh (closePos dekat 50) / FAKEOUT (breakout close balik ke tengah, wick lawan besar, candleAna lemah) / CHASE > 3.0 ATR dari swing (entry telat, harga sudah lari - WAJIB WAIT_FOR_RETRACE_TO_FVG) / MISSING_STRUCTURE_CONFIRMATION (mss NONE tanpa pengecualian fade) / fade tanpa volume climax (INVALID_FADE_NO_CLIMAX_VOLUME: butuh RSI6 ekstrem + volx >= 1.2 + wick_ratio_pct >= 40% bersamaan) / melawan arah besar TANPA tanda pelelahan apa pun.",
}

def _context(brief):
    """1 baris konteks minimal (bukan framing scoring — cuma label)."""
    src=str(brief.get('source',''))
    side=str(brief.get('side',''))
    sym=str(brief.get('symbol',''))
    gm=brief.get('godmode') or {}
    gml=f" GODMODE: {gm.get('line')}" if gm.get('line') else ""
    return f"Sinyal kurir: {sym} {side} (engine={src}).{gml} Payload JSON lengkap ada di state."

def build_questions(brief):
    """v10.1: SATU pertanyaan choice — bos analisis internal (PURE ATR + SuperFlow + MSS/FVG) lalu pilih."""
    q={"decision":{"type":"choice",
        "instructions":SYSTEM_IMMUNITY+"\n\n"+PERSONA_V7+"\n\nKONTEKS:\n"+_context(brief)+
            "\n\nAnalisis internal payload JSON sebagai scalper TRUE 5-menit: baca lembah/pucuk via RSI6 realtime + lensa anti-fakeout (closePos, retracePct, bbTouch, consec, candleAna), cek regime & BTC bias sebagai kekuatan gerak, identifikasi fakeout sebelum menembak. Payload.godmode = sensor kuantitatif GODMODE V2 dari Kurir: score 0-100 utk arah sinyal dgn tier SNIPER (>=90) / EXECUTE (>=75) / WATCH (>=71) / REJECT (<71) dan setup_type (TREND_CONTINUATION / MEAN_REVERSION) - pakai sebagai KOMPAS kuantitatif: SNIPER/EXECUTE = konfirmasi kuat utk menembak; WATCH/REJECT = hanya tembak kalau RSI6 & lensa anti-fakeout tetap kuat; jika godmode bertentangan keras dgn RSI6 realtime, jelaskan konfliknya di alasan sebelum memilih. Pilih opsi terakurat untuk TP 0.6-1.5% ke depan.",
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
