# P32 — TRADE RUBRIC (JEV Multi-Question Scoring)

> Status: **DIKUNCI / APPROVED oleh user (27 Sep 2026)** — BELUM DIIMPLEMENTASI.
> Nunggu topup TYPESAFE_API_KEY (JEV). Saat ini API JEV balas `HTTP 402 Payment Required`
> → **P35: FULL JEV NO-FALLBACK.** Tanpa model cadangan.
> **Begitu user bilang "udah topup", langsung eksekusi implementasi ini.**

---

## 1. Kenapa P32

Repo referensi:
- `monteduro/killmyidea` — 8 pertanyaan `score` 0–4 paralel dalam SATU request → weighted avg → KILL/FIX/SHIP
- `AkashPriyadarshii/jev-curate` — host-side pruning + adaptive token bucket + auto-429 backoff, 1500 baris/detik
- `browser-use/jev-ultrafast` — 1 request = 1 decision cycle, structured state (bukan screenshot)
- `lukaske/jev-doom-agent` — validasi `choice` + `probabilities` + `confidence`

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

### 2.3 RESILIENSI BOS (revisi user 28 Sep 2026 — MENGGANTIKAN "istirahat 10 menit")

- **402 (Payment Required)** → **notif TG topup** (sekali per jam, anti-spam P33).
  **P35: TANPA fallback** — keputusan DITUNDA sampai topup; scan & sistem tetap hidup,
  kandidat diulang di iterasi berikutnya.
- **429 (rate limit)** → **retry otomatis 3 detik** (sama dgn perilaku retry yang sudah ada),
  maksimal 2× per kandidat; kalau tetap gagal → kandidat dilewati + log (`jev_err`).
- **SEMUA model di .env kena 402** → BARU bot diem total (loop tetap jalan, tidak ada keputusan bos)
  dan kirim notif TG `🔴 SEMUA BOS 402 — BOT IDLE (butuh topup)`.
  **JANGAN bunuh diri / restart**: iterasi jalan terus tanpa llm_call → watchdog 900 dtk aman
  (obat akar insiden exit 99 + notif BOT START palsu).
- **Notifikasi real-time, bukan "BOT START"**: setiap perubahan status bos (402/429/recover)
  dikirim ke Telegram dgn data nyata (model mana, error apa, jam berapa).

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

### F. WICK-HUNTER (approved 28 Sep 2026 — dari The-Quant-Trading-Vault)

Tujuan user verbatim: "agar dia bisa lihat momentum signal chart pair mana yang
akan wick mau long & wick mau short (agar kita dapat signal early entry di
pucuk/lembah)". Kurir deteksi dulu (host-side, gratis), JEV nilai final.

**Sumber formula (strategi teruji, author ChaoZhang/TradingView):**
- `Hammer-and-Shooting-Star-Pattern-Trading-Strategy` — ATR filter + Fib 33.3%
- `Fundamental-Pinbar-Trading-Strategy` — pinbar + MA trend + SL 1.9×ATR, RR 3.1
- `Dual-Shadow-Reversal-Strategy` — candle tanpa shadow beruntun
- `Momentum-Exhaustion-Strategy` — Exhaustion oscillator: (C+H+L − MA(C+H+L)) / MA(C+H+L)

**Deteksi kurir (host-side, per pair per bar — NOL biaya API):**

```
c = candle terakhir (5m), rng = h-l, body = |c-o|
ATR14 = ATR 14-bar

1. WICK_REJECTION (inti):
   upper_wick = h - max(o,c) · lower_wick = min(o,c) - l
   pin_up   = upper_wick >= 2*body DAN upper_wick >= 0.55*rng  → "mau SHORT" (reject pucuk)
   pin_down = lower_wick >= 2*body DAN lower_wick >= 0.55*rng  → "mau LONG"  (reject lembah)

2. HAMMER / SHOOTING STAR (konfirmasi arah):
   hammer        = lower_wick >= 2*body DAN close >= o + 0.333*rng (close di atas fib 33.3%)
   shooting_star = upper_wick >= 2*body DAN close <= o + 0.333*rng
   (ATR filter: rng dalam 0.5×ATR … 2.5×ATR — buang candle abis/gidang)

3. EXHAUSTION OSC (lembah/pucuk terukur):
   ex_t  = (c+h+l) ; ex = (ex_t - MA20(ex_t)) / MA20(ex_t)
   ex > +X_atas → momentum over-extended (pucuk) ; ex < −X_bawah → lembah
   (X dikalibrasi dari data 30 hari per pair — jangan hardcode)

4. VOLUME CLIMAX:
   vol_ratio = v / MA20(v) ; climax = vol_ratio >= 2.0 PADA bar wick
   (wick + climax = rejection serius; wick tanpa volume = noise)

5. OUTPUT "wickHint" ke brief (2 arah):
   wickHint: {dir: 'SHORT'|'LONG'|'NONE', pattern: 'pin_up|pin_down|hammer|shooting_star',
              strength: 0-100, ex_score, vol_ratio}
   strength = weighted(ukuran wick, posisi di range, ex_score, vol_ratio)

**Persona JEV (tambahan langkah WICK-HUNTER):**
- wickHint searah sinyal + strength ≥ 70 → boleh CONFIRMED (prefer TIGHT/NORMAL —
  ini entry EARLY di pucuk/lembah, SL ketat di balik wick)
- wickHint searah + strength 50-69 → butuh konfirmasi ke-2 (FVG/MSS) baru boleh CONFIRMED
- wickHint lawan sinyal + strength ≥ 70 → WAJIB REJECT (mengayunkan pisau ke wick lawan)
- nilai `strength` masuk hitungan rubric `timing_freshness` & `liquidity_risk`
- Nama kurir tak berubah: wickHint hanya DATA; keputusan tetap bos.

**Anti-false-signal (hard rule kurir):**
- Wajib ATR filter (candle gak gila) DAN close-complete (bukan bar berjalan)
- Di TREND kuat searah (1h), hint fade dikurangi bobotnya (fade melawan 1h = butuh strength lebih tinggi)
- Log semua wickHint → `dewa_live_log.jsonl` buat backtest akurasi pattern 30 hari

**Referensi tambahan:** The-Quant-Trading-Vault (brainbrick-trades) — 5.806 spec
terindeks di /tmp/vault (clone lokal). 47 file relevan pattern wick/reversal.
Kandidat pengembangan v2: engulfing-filter, harami, dual-shadow, momentum-exhaustion.

---

### G. SKILL TAMBAHAN DARI VAULT (bedah user 28 Sep — "cuma 47 dari 5.806?")

Jawaban: 47 itu CUMA keluarga wick/reversal. Setelah dikategorikan ulang SEMUA
5.806 file, ada 10 keluarga skill bernilai untuk bot. Diterima ke P32 (semua
host-side gratis, JEV tetap hakim):

| # | Skill | Sumber vault | Jml spec | Nilai buat bot |
|---|---|---|---|---|
| 1 | **ATR dynamic SL / trailing** (chandelier) | 320 spec | Masalah #1 bot: 1 SL = 6.6 win. SL = 1.5×ATR14, trail = chandelier 3×ATR — SL mengikuti volatilitas, bukan persen mati |
| 2 | **Multi-indicator CONSENSUS** (skor 0-100) | 356 spec | Konsep sama dgn Trade Rubric — 5+ indikator vote, bukan 1 sinyal. rubric_quality_setup dapat nilai mentahnya |
| 3 | **VWAP premium/discount** | 49 spec | Harga vs VWAP ±1σ/2σ: di bawah -2σ = diskon (LONG grade naik), di atas +2σ = premium (SHORT). Obat entry pucuk FIL/ARB |
| 4 | **Divergence RSI6** (regular+hidden) | 61 spec | Harga pucuk baru + RSI6 turun = divergence → timing_freshness turun / hint early-exit |
| 5 | **MTF alignment** (5m/15m/1h) | 193 spec | Bos lihat 3 TF sekarang → trend_alignment 3/3 2/3 1/3 |
| 6 | **Volume konfirmasi** (OBV/CVD/vol_x) | 159 spec | Sudah ada sebagian (vol_x, OBV) — tambah dry-up (volume kering sebelum breakout = jebakan) |
| 7 | **Volatility SQUEEZE** (BB dalam Keltner) | 15 spec | Kompresi = koin tidur → BREAKOUT
 nyusul. Squeeze ON + breakout vol_x≥2 = setup momentum terbaik; tanpa squeeze, breakout vol rendah = KILL |
| 8 | **Regime filter (ADX/chop)** | 73 spec | ADX<20 = chop → pakai aturan fade/mean-revert; ADX≥20 = trend → pakai aturan follow. Persona bos dapat regime ini eksplisit |
| 9 | **Session timing** (London/NY/Asia) | 11 spec | Volatilitas per sesi — timing session_fit rubric pakai data nyata, bukan tebakan |
| 10 | **Trend-pullback entry** | 78 spec | Entry saat pullback ke MA/dense-zone, bukan kejar candle (obat FOMO di atas) |

**PRIORITAS IMPLEMENTASI (urutan, bukan semua sekaligus):**
1. ATR-SL + chandelier trail (skill #1) — langsung obat matematika kekalahan
2. VWAP premium/discount (skill #3) — murah (klines sudah ada), obat pucuk
3. Squeeze + regime ADX (skill #7+8) — sinyal jadi punya konteks volatilitas
4. Divergence RSI6 (skill #4) — timing keluar/entry pucuk
5. Session timing (skill #9) — polish terakhir

Yang TIDAK diambil (dengan alasan): Grid/DCA/martingale (61+50 spec — melanggar
disiplin SL, dead-margin), MachineLearning (4 — overfit, tak bisa diaudit),
arbitrage/market-making (27+9 — butuh infra co-lo, bukan domain scalper 5m).

---

*Dokumen ini dikunci atas permintaan user. Jangan diubah tanpa ACC.*
