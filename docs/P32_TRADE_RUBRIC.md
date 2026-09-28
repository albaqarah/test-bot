# P32 — TRADE RUBRIC (JEV Multi-Question Scoring)

> Status: **DIKUNCI / APPROVED oleh user (27 Sep 2026)** — BELUM DIIMPLEMENTASI.
> Nunggu topup TYPESAFE_API_KEY (JEV). Saat ini API JEV balas `HTTP 402 Payment Required`
> → bot jalan pakai fallback lightvela.
> **Begitu user bilang "udah topup", langsung eksekusi implementasi ini.**

---

## 1. Kenapa P32

Repo referensi:
- `monteduro/killmyidea` — 8 pertanyaan `score` 0–4 paralel dalam SATU request → weighted avg → KILL/FIX/SHIP
- `AkashPriyadarshii/jev-curate` — host-side pruning + adaptive token bucket + auto-429 backoff, 1500 baris/detik
- `browser-use/jev-ultrafast` — 1 request = 1 decision cycle, structured state (bukan screenshot)
- `lukaske/jev-doom-agent` — validasi `choice` + `probabilities` + `confidence`, fallback ditandai terang-terangan

**Kondisi bot sekarang:** `jev_bridge.call_jev` cuma kirim **SATU** pertanyaan
(`decision` type `choice`, 4 opsi). Tiap kandidat = 1 HTTP request buat 1 bit informasi.
JEV (System One) mengizinkan **banyak pertanyaan paralel dalam 1 request, 0 output token** —
jadi ini pemborosan kapasitas, bukan keterbatasan model.

---

## 2. Spesifikasi

### 2.1 Payload baru (1 request, 8 score + 2 noul + 1 choice)

```python
"questions": {
  # --- 8 SCORE (0-4) → x25 → 0-100 ---
  "quality_setup":     {"type":"score","instructions": "... struktur MSS+FVG+volume rapi?"},
  "timing_freshness":  {"type":"score","instructions": "... sinyal masih awal atau sudah basi?"},
  "liquidity_risk":    {"type":"score","instructions": "... ada wick/sweep yang bisa nembus SL?"},
  "trend_alignment":   {"type":"score","instructions": "... searah BTC & TF 1h?"},
  "rr_quality":        {"type":"score","instructions": "... RR vs jarak SL ke struktur?"},
  "crowd_position":    {"type":"score","instructions": "... ini entry yang jelas/mudah di-sweep?"},
  "volatility_fit":    {"type":"score","instructions": "... SL cocok dengan ATR sekarang?"},
  "session_fit":       {"type":"score","instructions": "... jam trading (Asia/EU/US) cocok?"},

  # --- 2 NOUL (probabilitas) ---
  "is_inverted":       {"type":"noul","instructions": "... sinyal ini kebalik arah?"},
  "is_fresh":          {"type":"noul","instructions": "... momentum belum habis?"},

  # --- 1 CHOICE (varian eksekusi, seperti sekarang) ---
  "decision":          {"type":"choice","criteria": {CONFIRMED_TIGHT, CONFIRMED_NORMAL,
                                                     CONFIRMED_WIDE, REJECT}}
}
```

### 2.2 Skor & gate

- tiap score 0–4 → ×25 → 0–100
- **weighted average**, bobot default (bisa di-override `.env`):
  - `timing_freshness` ×2  (ajaran P28 anti-telat)
  - `liquidity_risk` ×2    (penyebab SL terbanyak)
  - sisanya ×1
- **Verdict:**
  - `< 50` → **KILL** — auto-reject, masuk `done` (jangan tanya ulang)
  - `50–64` → **FIX/WAIT** — REJECT-await
  - `>= 65` → **SHIP** — boleh CONFIRMED (varian dari `decision`)
- **Hard rule (override):** kalau `is_inverted > 0.5` → KILL berapapun skornya
  (kasus NEAR SHORT di lembah 26 Sep 19:39, BCH LONG inversion)
- **Hard rule:** kalau `is_fresh < 0.35` → maksimum FIX, tidak bisa SHIP

### 2.3 Hemat API (dari jev-curate)

- **Host-side pruning** SEBELUM panggil JEV: buang kandidat dengan
  volume mati / regime ngaco / jarak SL tak masuk akal → nol biaya API
- **Adaptive backoff**: saat `402` / `429` / timeout → istirahat 10 menit
  (BUKAN retry 3 detik). Ini obat langsung buat insiden watchdog 900 dtk
  yang bikin bot bunuh diri (`os._exit(99)`) lalu PM2 restart → notif BOT START palsu.

---

## 3. Peta implementasi (saat dieksekusi nanti)

| File | Perubahan |
|---|---|
| `jev_bridge.py` | payload `questions` diperluas (8 score + 2 noul + 1 choice); parser skor; helper `rubric_score()` |
| `dewa_live.py` | gate baru pakai skor 0–100; host-side pruning sebelum `llm_call`; adaptive backoff saat 402/429 |
| `tg_notify.py` | notif entry tampilkan `RUBRIC 78/100 · SHIP` + 2 sinyal terkuat/terlemah |
| `smc_engine.py` | (opsional) sediakan fitur ATR/volatility buat `volatility_fit` |
| `.env.example` | `RUBRIC_MIN_SHIP=65`, `RUBRIC_MIN_FIX=50`, bobot override |

## 4. Cara verifikasi (wajib, sebelum klaim sukses)

1. `py_compile` semua file + import chain (termasuk `v15_grade.py` via `spec_from_file_location`)
2. Unit test offline: payload contoh → skor & verdict benar (tanpa API)
3. Test live 3 skenario: setup sempurna → SHIP; sinyal basi → FIX; sinyal kebalik → KILL
4. Cek log `err` = nol setelah restart PM2
5. Commit + push ke `master` (branch bukan main!)

---

*Dokumen ini dikunci atas permintaan user. Jangan diubah tanpa ACC.*
