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
| `dewa_live.py` | gate baru pakai skor 0–100; host-side pruning sebelum `llm_call`; adaptive backoff saat 402/429; **fetch A–D (candle shape, depth, funding/OI, MTF) dgn timeout 8s + cache 30 dtk** |
| `market_snapshot.py` | **BARU** — helper terpisah: ambil & cache data A–D, hitung turunan (engulfing, wick_ratio, imbalance, wall, oi_change), return dict siap tempel ke `brief` |
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

## 2.4 PEMAHAMAN PASAR YANG DIPERLUAS (approved 27 Sep 2026)

Masalah: kurir sekarang cuma kirim ~8 field mentah (P1-P8). JEV gak bisa "lihat"
bentuk candle, kedalaman order book, atau posisi crowded — dia cuma baca ringkasan.
P32 juga memperkaya **apa yang dikirim**, tetap dalam 1 request yang sama.

### A. Bentuk candle (5 candle terakhir, TF 5m)
```
candles_5m: [
  {o:0.3512, h:0.3521, l:0.3501, c:0.3518, v:1.24, spread:0.0057, body:0.0006, up_wick:0.0003, dn_wick:0.0017},
  ... 4 candle sebelumnya
]
```
Turunan otomatis di kurir: `engulfing`, `hammer/shooting_star`, `doji`, `higher_highs`,
`wick_ratio` (sumbu vs body). JEV baca pola ini buat `quality_setup` & `liquidity_risk`.

### B. Order-book imbalance (Binance depth, limit 100)
```
book: {bid_vol: 12.4, ask_vol: 8.1, imbalance: +0.21,
       wall_bid: 0.3490, wall_ask: 0.3535, spread_bps: 1.2}
```
- `imbalance > +0.15` → dukung LONG · `< -0.15` → dukung SHORT
- `wall_*` = dinding terbesar → jadi referensi SL/TP (jangan taruh SL tepat di dinding)
- Sumber: `GET /fapi/v1/depth?symbol=X&limit=100` (timeout 8s, cache 30 dtk)

### C. Funding rate + Open Interest
```
deriv: {funding: -0.00012, funding_trend: 'falling', oi_change_1h: +4.2%}
```
- funding sangat negatif + OI naik → SHORT crowded → risiko **short squeeze** → hati-hati SHORT
- funding sangat positif + OI naik → LONG crowded → risiko **long squeeze** → hati-hati LONG
- Sumber: `GET /fapi/v1/premiumIndex` + `GET /fapi/v1/openInterest` (historis via `/futures/data/openInterestHist`)
- Dipakai buat skor `crowd_position`

### D. Multi-timeframe (5m + 15m + 1h)
```
mtf: {
  "5m":  {regime:'TREND_UP',  rsi6:63.8, mss:'BULLISH', trend_dir:'up'},
  "15m": {regime:'RANGE',     rsi6:55.1, mss:'NONE',    trend_dir:'side'},
  "1h":  {regime:'TREND_UP',  rsi6:58.4, mss:'BULLISH', trend_dir:'up'}
}
```
- `trend_alignment` dihitung dari keselarasan 3 TF: 3/3 searah = 4 · 2/3 = 2 · 1/3 atau kontra = 0
- Ini menggantikan tebakan "regime BTC 1h" yang sekarang cuma 1 field

### E. Catatan biaya & keamanan
- Semua data A–D **gratis** (endpoint publik Binance) & masuk ke request JEV yang sama
  → **nol tambahan biaya API JEV** (System One: input murah, 0 output token)
- Wajib **timeout 8s + cache 30 dtk** per simbol: jangan sampai nambah latency sampai
  kena watchdog 900 dtk (insiden exit 99 → restart → notif BOT START palsu)
- Kalau endpoint gagal → field di-skip (None), JEV tetap dinilai dengan data yang ada;
  **jangan** batalkan seluruh keputusan gara-gara 1 sumber error

---

*Dokumen ini dikunci atas permintaan user. Jangan diubah tanpa ACC.*
