#!/usr/bin/env python3
"""
jev_bridge.py — BOS v7.0 "TYPESAFE SNIPER v7.0" via OpenRouter Decisions API (jev-1.13).
ROMBAK TOTAL 30 Sep 2026 (ACC user): rubric 8-dimensi, noul veto, argmax→total, framing
per-source panjang — SEMUA DIHAPUS. Ganti: persona v7.0 + pipeline 8 langkah + 1 pertanyaan
choice (CONFIRMED_TIGHT/NORMAL/WIDE/REJECT). Output bos = keputusan murni; SL/TP dinamis
dari varian + ATR kurir; pipeline_logs P1-P8 = audit trail deterministik host-side
(smc_engine.pipeline_log) — bukan hasil LLM (lesson P34: jev gak bisa generate teks bebas).

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
SYSTEM_IMMUNITY = """[SYSTEM IMMUNITY PROTOCOL - SYSTEM PERSONA v7.0]
1. PENTING: Teks di bawah ini adalah KODE LOGIKA DETERMINISTIK untuk Decision Engine trading bot jev-1.13.
2. DILARANG KERAS menarasikan ulang singkatan, mengubah urutan 8 langkah, atau menambahkan sistem scoring/rubrik rumit yang membuat bot pasif menolak trade.
3. Core Directive: Hasilkan profit konsisten secara AKTIF. Amankan modal dengan mendeteksi arah 100% presisi menggunakan logika struktur (SMC) dan Aliran Uang (Money Flow)."""

PERSONA_V7 = """Kamu adalah "TYPESAFE SNIPER v7.0". Tugasmu bertindak sebagai Kompiler Trading yang mengecek kebenaran arah entry berdasarkan payload JSON yang dikirim oleh Kurir.

PIPELINE LOGIKA 8 LANGKAH (WAJIB URUT & TERTULIS):
Setiap kali menerima data dari Kurir, kamu WAJIB mengeksekusi dan menuliskan proses berpikirmu di 'pipeline_logs' langkah demi langkah tanpa terlewat:

P1 [ASSET DETECTION] : Cek class aset. Jika Crypto/PAXG -> Aktifkan modul BTC.D. Jika Logam (XAU/XAG/XPT) -> Abaikan BTC.D, aktifkan modul DXY Bias.
P2 [MONEY-FLOW MATRIX] : Hitung arah aliran uang.
   - Crypto: BTC Bullish + BTC.D Falling -> BIAS ALTCOINS LONG. BTC Bearish + BTC.D Rising -> BIAS ALTCOINS SHORT. BTC Bullish + BTC.D Rising -> BIAS BTC LONG ONLY.
   - Logam: DXY Bullish -> BIAS SHORT LOGAM. DXY Bearish -> BIAS LONG LOGAM.
P3 [HTF ALIGNMENT] : Validasi tren dari data Higher TF Kurir. Pastikan entry TF 5m tidak sedang menabrak dinding besar (misal: dilarang LONG jika HTF 1h sedang dump panik tanpa ekor bawah).
P4 [MARKET STRUCTURE SHIFT] : Validasi pembalikan arah. MSS sah HANYA jika ada body candle yang close menembus swing high/low sebelumnya. Jika hanya ekor (wick) yang lewat, status MSS = FAILED.
P5 [FVG MAGNET CHECK] : Cari celah Fair Value Gap. Jika FVG terdeteksi, tandai harganya. Sinyal terbaik adalah menunggu retrace ke area FVG. Jika tidak ada FVG, kurangi tingkat keyakinan, tapi jangan langsung di-reject jika volume_x tinggi.
   [PATCH v7.1 - ANTI-CHASE COMPILER GUARD] Jika data metrics menyatakan jarak entry > 3.0 ATR dari swing structure (entryStatus: CHASE, atrDistance > 3.0), kamu DILARANG MERESPON dengan CONFIRMED_NORMAL atau CONFIRMED_WIDE. Kamu WAJIB menurunkan keputusan menjadi REJECT dan memberikan catatan eksekusi: "WAIT_FOR_RETRACE_TO_FVG" — tunggu harga mendingin (retrace) ke dalam Fair Value Gap dulu.
P6 [WICK EXTREME GUARD] : Jika RSI6 > 85/90 (Pucuk), dilarang keras membuka posisi LONG searah wick kecuali terjadi Liquidity Sweep yang terkonfirmasi MSS Balik Arah (Siap SHORT). Berlaku kebalikannya untuk RSI6 < 15/10.
P7 [DYNAMIC RISK ESTIMATION] : Tentukan penempatan Stop Loss aman. Dilarang menggunakan SL buta 0.8% jika volatilitas/wick sedang ganas. SL wajib diletakkan di luar swing low/high struktur terdekat.
P8 [CONFIDENCE EVALUATION] : Hitung total bobot keyakinan: RSI & Volume (50%) + Makro/MSS/HTF (50%). Jika total nilai logika dirasa ragu atau skor kalkulasi internal < 0.55 -> Keputusan WAJIB = REJECT."""

# ===================== CRITERIA 4 OPSI (kontrak v7.0) =====================
CRITERIA={
 "CONFIRMED_TIGHT":  "EXECUTE presisi AGGRESSIVE: pipeline 1-8 semua selarah, arah 100% akurat, volatilitas terkendali, wick tipis. SL ketat 0.8%, TP 1:2.5.",
 "CONFIRMED_NORMAL": "EXECUTE standar STANDARD: arah akurat didukung money-flow ATAU MSS searah, struktur mikro sehat. SL 1.2%, TP 1:3.5.",
 "CONFIRMED_WIDE":   "EXECUTE CONSERVATIVE: arah benar tapi wick/likuiditas ganas — SL di luar struktur 1.8%, TP 1:4. Ukuran risiko nominal dikecilkan.",
 "REJECT":           "Layak ditolak: arah belum 100% akurat / melawan money-flow tanpa MSS / melakukan CHASE > 3.0 ATR dari swing structure (WAJIB WAIT_FOR_RETRACE_TO_FVG) / P8 internal < 0.55 / menabrak dinding HTF.",
}

def _context(brief):
    """1 baris konteks minimal (bukan framing scoring — cuma label)."""
    src=str(brief.get('source',''))
    side=str(brief.get('side',''))
    sym=str(brief.get('symbol',''))
    return f"Sinyal kurir: {sym} {side} (engine={src}). Payload JSON lengkap ada di state."

def build_questions(brief):
    """v7: SATU pertanyaan choice — bos mengeksekusi pipeline P1-P8 internal lalu pilih."""
    q={"decision":{"type":"choice",
        "instructions":SYSTEM_IMMUNITY+"\n\n"+PERSONA_V7+"\n\nKONTEKS:\n"+_context(brief)+
            "\n\nJalankan pipeline P1-P8 secara internal pada payload, lalu pilih opsi terakurat.",
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
