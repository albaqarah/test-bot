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

# ===================== v12.1 REAL PROBABILITY RUBRIC (revive era P34, ACC user) =====================
# Bukti 48 jam: conf self-report LLM WIN 35.9 vs LOSE 33.9 = NOISE, tanpa nilai prediksi.
# Ganti: bos jawab 8 rubric 0-4 + 2 noul dlm request yg sama (biaya sama), skor 0-100
# DIHITUNG HOST dari kriteria teks = real probability. Bobot timing & fakeout x2 (jantung scalper).
RUBRIC_V12=[
 ("rs_quality","KUALITAS SETUP","Kualitas setup keseluruhan berdasar payload",
  ["0 = Sinyal sampah: hampir semua lapisan melawan",
   "1 = Lemah: 1-2 bukti pendukung saja",
   "2 = Medioker: bukti campur, tidak yakin",
   "3 = Bagus: mayoritas lapisan searah",
   "4 = Sempurna: RSI6 ekstrem + closePos ujung + volx climax + MSS/FVG searah"]),
 ("rs_timing","TIMING & FRESHNESS (bobot 2x)","Segar tidaknya entry di pucuk/lembah",
  ["0 = Telat: CHASE jauh dari swing (atrDistance > 3 ATR)",
   "1 = Ketinggalan: gerakan utama lewat, retracePct sudah dalam",
   "2 = Netral: harga di tengah jalan (entryStatus MID)",
   "3 = Cepat: baru berbalik, retracePct mulai > 0",
   "4 = Lemparan awal di pucuk/lembah: AT-TURN + RSI6 ekstrem + retrace baru mulai"]),
 ("rs_fakeout","ANTI-FAKEOUT LENS (bobot 2x)","Kejujuran candle: bukan jebakan breakout",
  ["0 = FAKEOUT klasik: closePos dekat 50 + wick lawan besar + candleAna lemah",
   "1 = Sinyal leleh: closePos 40-60, arah ragu",
   "2 = Netral: closePos agak ujung tapi tanpa bbTouch",
   "3 = Kuat: closePos jauh dr 50 searah, candleAna tebal",
   "4 = Murni: closePos ekstrem (>85/<15) + bbTouch searah + consec masih muda (<5)"]),
 ("rs_trend","TREND & MONEY-FLOW ALIGNMENT","Keselarasan 15m/1h + BTC bias + SuperFlow",
  ["0 = Melawan BTC bias dan HTF tanpa tanda pelelahan",
   "1 = Lawan mayoritas lapisan",
   "2 = Campur: ada tanda pelelahan tapi lemah",
   "3 = Mayoritas searah / kontra dgn pelelahan jelas + climax",
   "4 = Searah penuh: HTF + BTC bias + money flow satu arah"]),
 ("rs_rr","RR & LOKASI ENTRY","Kualitas risk-reward dari lokasi",
  ["0 = Entry tengah range / lokasi jelek",
   "1 = Lokasi bawah standar",
   "2 = RR standar",
   "3 = Bagus: dekat FVG/zona kunci",
   "4 = Tepat di ekstrem: SL 0.5x ATR masih di balik struktur mikro"]),
 ("rs_vol","VOLATILITY FIT","Cocok tidaknya volatilitas dgn scalp 5m & TP 0.6-1.5%",
  ["0 = Volatilitas mati (volx kopong, 1x ATR gak cukup utk TP 0.6%)",
   "1 = Vol tidak cocok utk scalp",
   "2 = Vol normal",
   "3 = Vol sehat: 1x ATR 5m mencukupi TP band",
   "4 = Sempurna: climax volume (volx >= 1.5) searah dgn ATR pas utk TP 0.6-1.5%"]),
 ("rs_struct","STRUKTUR MIKRO (MSS/FVG)","Kualitas struktur SMC 5m",
  ["0 = Struktur melawan arah (MSS lawan)",
   "1 = Struktur lemah/abu-abu",
   "2 = Netral (MSS NONE tapi fade beralasan)",
   "3 = MSS searah",
   "4 = MSS + FVG searah sekaligus"]),
 ("rs_regime","REGIME FIT","Kecocokan arah dgn regime pasar",
  ["0 = Kontra regime keras tanpa konfirmasi",
   "1 = Kontra regime dgn konfirmasi tipis",
   "2 = Netral (RANGE, fade ujung)",
   "3 = Searah regime",
   "4 = Searah regime + ekstrem RSI6 = peluang ganda"]),
]

def rubric_total(ans):
    """v12.1: total rubric 0-100 (timing & fakeout x2). Return (total, detail) atau (None,{})."""
    tot=0.0; maxw=0.0; detail={}
    for name,label,inst,crit in RUBRIC_V12:
        a=ans.get(name) or {}
        val=None
        for k in ('score','value','choice','confidence'):
            if isinstance(a.get(k),(int,float)): val=float(a[k]); break
            if isinstance(a.get(k),str):
                try: val=float(a[k]); break
                except Exception: pass
        if val is None: return None,{}
        val=max(0.0,min(4.0,val))
        w=2.0 if name in ('rs_timing','rs_fakeout') else 1.0
        tot+=val*w; maxw+=4.0*w
        detail[name]=round(val,1)
    if maxw<=0: return None,{}
    total=round(tot/maxw*100)
    # noul veto (P34 verbatim): rata2 noul >= 0.75 = risiko gugur/flip ekstrem -> potong 20 poin
    nv=[float(a.get('noul')) for a in (ans.get('noul_invalidate'),ans.get('noul_flip'))
        if isinstance(a,dict) and isinstance(a.get('noul'),(int,float))]
    if nv:
        detail['noul_risk']=round(sum(nv)/len(nv),2)
        if sum(nv)/len(nv)>=0.75: total=max(0,total-20)
    return total, detail

def _context(brief):
    """1 baris konteks minimal (bukan framing scoring — cuma label)."""
    src=str(brief.get('source',''))
    side=str(brief.get('side',''))
    sym=str(brief.get('symbol',''))
    return f"Sinyal kurir: {sym} {side} (engine={src}). Payload JSON lengkap ada di state."

def build_questions(brief):
    """v12.1: 1 choice + 8 score rubric + 2 noul = 11 jawaban dlm SATU request (biaya sama, era P32)."""
    q={"decision":{"type":"choice",
        "instructions":SYSTEM_IMMUNITY+"\n\n"+PERSONA_V7+"\n\nKONTEKS:\n"+_context(brief)+
            "\n\nAnalisis internal payload JSON sebagai scalper TRUE 5-menit: baca lembah/pucuk via RSI6 realtime + lensa anti-fakeout (closePos, retracePct, bbTouch, consec, candleAna), cek regime & BTC bias sebagai kekuatan gerak, identifikasi fakeout sebelum menembak. Pilih opsi terakurat untuk TP 0.6-1.5% ke depan.",
        "criteria":CRITERIA}}
    for name,label,inst,crit in RUBRIC_V12:
        q[name]={"type":"score","instructions":f"{label} — {inst}. Pilih SATU angka 0-4 dari kriteria.","criteria":crit}
    q["noul_invalidate"]={"type":"noul","instructions":"Seberapa besar RISIKO trade ini GUGUR (invalidasi)? 0=tidak ada, 1=hampir pasti gugur."}
    q["noul_flip"]={"type":"noul","instructions":"Seberapa mudah bias ini KEBALIK oleh sinyal baru? 0=sangat stabil, 1=sangat rapuh."}
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

    # v12.1: confidence = REAL PROBABILITY (skor rubric 0-100 dihitung HOST di bawah) —
    # bukan self-report LLM (bukti 48 jam: WIN 35.9 vs LOSE 33.9 = noise).
    out={"decision":"REJECT","variant":"","confidence":0,
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
        out["confidence"]=100  # deterministic host rule (pucuk/lembah absolut) — bukan self-report
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
    # ===== [v12.1 REAL PROBABILITY GATE - HOST COMPUTED] =====
    # Skor 0-100 dihitung HOST dr 8 rubric + 2 noul (kriteria teks -> angka). Gate era P34:
    # <50 KILL, 50-64 WAIT (CONFIRMED dibuang), >=65 SHIP. Fail-open: rubric tak terjawab
    # utuh -> total None -> keputusan choice diteruskan (conf 0, dilaporkan).
    total, detail = rubric_total(ans)
    out["rubric"]=total
    if total is not None: out["rubric_detail"]=detail
    if total is not None and out["decision"]=="CONFIRMED":
        if total<50:
            out["decision"]="REJECT"; out["variant"]=""
            out["reason"]=f"RUBRIC KILL {total}<50 (real-prob): {detail}"
            return out
        if total<65:
            out["decision"]="REJECT"; out["variant"]=""
            out["reason"]=f"RUBRIC WAIT {total} 50-64 (real-prob): {detail}"
            return out
    if total is not None:
        out["confidence"]=total
        tag=f" [rubric {total}]" + (f" [noul {detail.get('noul_risk')}]" if 'noul_risk' in detail else "")
    else:
        tag=" [rubric None]"
    if out["decision"]=="CONFIRMED":
        out["reason"]=f"bos v12 CONFIRMED_{out['variant']} (p: {pj}){tag}"
    else:
        # Ragu-ragu yang layak REJECT tetap sah (P8) — tapi laporkan penuh
        out["reason"]=f"bos v12 REJECT (p: {pj}){tag}"
    return out

if __name__=='__main__':
    # smoke offline: build_questions (TANPA API call)
    b={"symbol":"BTCUSDT","side":"SHORT","source":"fade","asset":{"class":"CRYPTO"}}
    qs=build_questions(b)
    print('questions:', list(qs.keys()), '| criteria:', list(qs['decision']['criteria'].keys()))
    print('persona len:', len(SYSTEM_IMMUNITY)+len(PERSONA_V7), 'chars | 1 pertanyaan, 4 opsi — kontrak v7.0 OK')
