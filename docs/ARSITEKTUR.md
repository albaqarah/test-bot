# ARSITEKTUR PENUH — DEWA Bot v6.7 (P39)

> Dibuat 30 Sep 2026 atas permintaan user: jabaran lengkap sistem KURIR & BOS,
> semua persona & skill, alur kerja end-to-end, plus potongan kode kunci.
> Sumber: bacaan ulang kode live (commit 5852200). Bukan dari ingatan.

---

## 0. PETA BESAR

```
[BINANCE fapi]──► v15_grade.py (fetch klines semua TF, grade utils)
        │
════════╪═══════════════ KURIR (host-side, 100% matematika, GRATIS) ═════════
        │
        ├─ reversion_bot.py   : FADE ekstrem (beli lembah RSI<25, jual pucuk RSI>75)
        ├─ hybrid_rules.py    : TREND-pullback + SCALP P8-REV + P6-loose (off)
        ├─ market_snapshot.py : 13 sensor pasar + WICK-HUNTER + ENTRY-LOC + slSuggest
        ├─ smc_engine.py      : MSS / FVG / Likuiditas / BTC.D proxy / DXY / money-flow
        ├─ dewa_skill.py      : briefing + scalper pack (KDJ, StochRSI, OBV, chart spark)
        ├─ tradfi_session.py  : gate sesi CME (XAU/XAG/XPT/PAXG)
        │
        │   GATES (urutan, murah → mahal):
        │   1. freshness   : scalp harus muda ≤4 bar (20 mnt), lainnya ≤24 bar
        │   2. done dedup  : (sym, bar_ts, side) — trim by ts, cap 2000 (P39)
        │   3. reject_cd   : 15 menit per (sym, side) — PERSISTENT (P39 fix)
        │   4. posisi      : 1 posisi/pair, max 5 slot global, cooldown 30 mnt/pair
        │   5. skip_dry    : volume kering dibunuh — KECUALI wick-hint dir+str≥55 (P38a)
        │   6. tradfi      : blok 3 jam sebelum open/close CME
        ▼
   BRIEFING JSON (satu paket kaya data per kandidat)
        │
════════╪═══════════════ BOS (jev-1.13, OpenRouter Decisions API, ~$0.0000165/keputusan) ═══
        │
        ├─ PERSONA   : TYPESAFE SNIPER v3.5 — pipeline 10 langkah WAJIB berurutan
        ├─ FRAMING   : per-source (fade=taruhan balik arah wajib bukti balik /
        │              trend=pullback lanjutan / p6=fade longgar harus lebih galak /
        │              scalp=momentum LANJUTAN, oversold bukan alasan nolak)
        ├─ 11 PERTANYAAN 1 REQUEST:
        │     1× choice  : CONFIRMED_TIGHT / CONFIRMED_NORMAL / CONFIRMED_WIDE / REJECT
        │     8× score   : rubric 0-4 (quality, timing×2, liquidity×2, trend, rr,
        │                 crowd, vol, session)
        │     2× noul    : risiko gugur + mudah flip (0-1)
        ├─ MATEMATIKA KEPUTUSAN:
        │     conf      = Σ p(CONFIRMED_*)  ×100
        │     P38-D     : kalau pilihan argmax = REJECT tapi ΣCONFIRMED > p(REJECT) dan ≥0.50
        │                 → CONFIRMED (varian p tertinggi) — obat split-vote
        │     RUBRIC    : total 0-100; <50 = KILL (paksa REJECT); 50-64 = WAIT (REJECT-await);
        │                 ≥65 = SHIP. noul rata-rata ≥0.75 → total −20
        │     MIN_CONF  : conf < 55 (.env) → REJECT (kandidat tak dikunci, boleh ditanya lagi)
        ▼
   CONFIRMED + varian
        │
════════╪═══════════════ EKSEKUTOR (dewa_live.py, mode DRY virtual) ═════════════════════════
        │
        ├─ P16-B WICK-FLIP   : LONG di-RSI6>90 → flip SHORT (dan mirror <10)
        ├─ SL/TP per varian  : TIGHT 0.8%/1:2.5 · NORMAL 1.2%/1:3.5·4 · WIDE 1.8%/1:4
        ├─ ATR-SL (P32)      : SL minimum ikut ATR14×1.5 (clamp 0.8–2.4%) bila lebih lebar
        ├─ RANGE GUARD (P19-style) : SL di dalam range 6 jam → dipaksa WIDE
        ├─ SANITY (P36)      : SL dipaksa 0.3–3.0% dari entry — mematikan kelas bug satuan
        ├─ TRAIL-LOCK (P10b) : profit ≥0.6% → SL nempel di (puncak −0.3%), naik terus
        ├─ MAXHOLD           : trend 480 bar (40 jam) · chop 96 bar (8 jam) → exit TIME
        └─ NOTIF TG          : entry/exit/rekap + reasoning bos + baris lokasi 🎯/⚠️
```

Filosofi: **kurir miskin opini, kaya data** — dia cuma setor kandidat + bukti.
**bos = satu-satunya pengambil keputusan** (FULL JEV NO-FALLBACK — jev error =
kandidat dilewati, diulang iterasi berikut; TIDAK ADA model fallback).
**eksekutor = disiplin** — kekalahan dipotong SL, kemenangan dikunci trail-lock.

---

## 1. KURIR — 4 MESIN SINYAL (+1 opsional)

### 1a. FADE ekstrem (`reversion_bot.gen_signals`) — engine paling sesuai filosofi bos
```
LONG  jika RSI6 < 25  AND z-score(200 bar) < −1.5  AND imb ≤ −0.15   (lower-wick climax)
SHORT jika RSI6 > 75  AND z-score > +1.5            AND imb ≥ +0.15   (upper-wick climax)
grade A jika vol_x > 1.5 AND imb ekstrem (≤−0.3 / ≥+0.3); selain itu B
```
- `imb` (imbalance) = ((min(o,c)−l) − (h−max(o,c))) / range → makin negatif makin berat ekornya bawah.
- Regime 1h dipakai bos (bukan kurir) sebagai konteks; anti falling-knife via bos.
- Ini engine yang nembak AAVE LONG RSI6 20.9 & TRX SHORT 86.9 pagi 30 Sep — LOKASI-nya benar (lembah/pucuk beneran).

### 1b. TREND-pullback (`hybrid_rules.gen_trend_signals`)
```
TREND_UP : c > EMA20(1h) dan EMA20(15m) > EMA20(1h)
           → LONG saat harga nyentuh EMA20(15m), close hijau, RSI6 35-60,
             lower-wick ≥40% range, vol_x > 1.0
TREND_DOWN: mirror utk SHORT (RSI6 40-65, upper-wick)
grade A jika vol_x>1.5 dan wick≥55%
```

### 1c. SCALP P8-REV (`hybrid_rules.gen_scalp`) — momentum, 3 trigger (salah satu):
1. StochRSI(14 dari RSI6) belok dari ekstrem: >80 turun → SHORT; <20 naik → LONG
2. RSI6 belok dari ekstrem: >80 turun / <20 naik (persis layar scalper)
3. Breakout: vol_x > 2.5 + body >60% range searah
```
Konfirmasi vol_x ≥ 1.2 · OBV soft-veto: hanya menolak jika aliran 10-bar
MELAWAN KERAS (>3× avg volume) — bukan sekadar negatif.
P12 ANTI-PUCUK: breakout LONG dilarang kalau RSI6 > 85 (mirror SHORT < 15).
```
⚠️ Catatan jujur: engine INI yang di pasar mati dominan nembak sinyal RSI netral
(45–56) tanpa edge lokasi — 13/23 kandidat pagi 30 Sep dari sini. Bos bunuh semua.

### 1d. P6 loose fade (`gen_loose_fade`) — default OFF (`P6_LOOSE=off`)
z≥3.0 bypass imb, atau RSI 70/30 + z>2.5 + imb standar. Selalu grade B.

### 1e. Dedupe & konflik (`gen_hybrid`)
- Arah bentrok di bar yang sama → bar dibuang (kabut).
- Dua engine sepakat → grade naik A. Source engine pertama disimpan (`src`) untuk framing bos.

### 1f. WICK-HUNTER (`market_snapshot.wick_hunter`) — mata pucuk/lembah
```
pattern  : shooting_star/SHORT, hammer/LONG, pin_up/pin_down (uw/lw ≥2×body, ≥55% range,
           close di sepertiga yang tepat), hanya jika atr_ok (range 0.5–2.5× ATR)
strength = 0.40·wick_dom + 0.20·pos + 0.25·exhaustion + 0.15·volume  (×100)
penalty  : SHORT saat RSI6<70 → ×0.85; LONG saat RSI6>30 → ×0.85 (belum ekstrem)
dir=NONE kalau tak ada pola valid — strength tanpa arah = tidak lolos gate P38a
```

### 1g. ENTRY-LOC (`market_snapshot.entry_loc`, P38-C) — pelajaran studi 182 trade
```
swing = high/low 30 bar terakhir; dist = (swing−close)/ATR14
AT-TURN : ≤1.5 ATR dari swing searah sinyal  (WR historis 76.5% — satu-satunya bucket plus)
MID     : 1.5–3 ATR
CHASE   : >3 ATR (ngejar — WR 68.5%, minus)
```
Dikirim ke bos + dicetak di notif (🎯/⚠️). INSTRUKSI, bukan palang mekanis.

### 1h. Sensor lain (`market_snapshot.enrich_market`)
atr_pct · slSuggest (ATR14×1.5, clamp 0.8–2.4%) · vwap/vwap_sigma/vwap_z ·
squeeze (BB-KC) · adx14 + regime_strength · mtf 5m/15m/1h (regime+rsi6+dir+score) ·
divergence_rsi6 · dry_up · session_wib · depth_imb (book imbalance + wall) · oi_delta ·
candle_shapes (5 bar closed terakhir).

### 1i. SMC (`smc_engine.enrich`)
- **MSS**: close menembus swing fractal 2-2 terakhir → MSS_BULLISH/BEARISH (reversal sah HANYA jika close-break, bukan wick).
- **FVG**: celah 3-candle + status FORMED/MITIGATED + range.
- **Likuiditas**: SWEPT bila 60 bar terakhir nembus high/low 100 bar sebelumnya.
- **BTC.D proxy**: share volume BTC dari top-20 (cache 60 dtk, fallback ringan weight 12).
- **DXY**: via tv_bridge (best-effort, khusus logam).
- **moneyFlow**: matriks teks untuk bos — BULLISH+RISING=BTC saja, BULLISH+FALLING=LONG alts,
  BEARISH+RISING=SHORT alts, BEARISH+FALLING=short-bias total, SIDEWAYS+FALLING=rotasi alts.
- Audit trail P1–P8 per keputusan (asset, moneyflow, mss, fvg, wick/rsi6, risk, budget, freshness).

---

## 2. BOS — jev-1.13 (Decisions API)

### 2a. Persona: TYPESAFE SNIPER v3.5 (jev_bridge.PERSONA)
Pipeline WAJIB berurutan, dilarang lompat:
1. **Deteksi aset** — CRYPTO baca BTC.D; TRADFI_METAL baca DXY (dolar naik = SHORT logam).
2. **Money-flow matrix** — sinyal melawan arah uang butuh bukti mikro kuat.
3. **MSS** — reversal sah hanya close-break swing; candle besar tanpa close-break = jangan asumsi balik.
4. **FVG** — jangan kejar harga terbang; ideal: MSS → retrace ke FVG → entry. NONE bukan larangan.
5. **Wick extreme** — jangan counter wick buta; fade butuh makro searah; liquidity sweep + makro = manipulasi.
6. **Kontrak SL/TP** — SL 0.8% dilarang saat wick ganas; pakai slSuggest sbg patokan; WIDE 1:4 utk wick kejam.
7. **Confidence budget** — RSI6 20% + volume 30% + makro/MSS 50%; Σp CONFIRMED <0.55 → REJECT.
8. **Kering/telat** — momentum_class 'kering' atau sinyal >20 menit → REJECT.
9. **WICK-HUNTER** — searah + ≥70 + climax = MENGUAT (boleh CONFIRMED TIGHT/NORMAL);
   searah 50-69 = butuh konfirmasi ke-2; LAWAN ≥70 = WAJIB REJECT; NONE/<50 = abaikan.
10. **Market snapshot** — vwap_z ≤−2 diskon (bagus LONG), ≥+2 premium (bagus SHORT);
    squeeze+breakout = momentum terbaik; CHOP→fade, TREND→follow-through; mtf 1/3 = butuh bukti ekstra.

### 2b. Framing per-source (`_framing`) — kunci adil menilai tiap keluarga sinyal
- **fade** (P38-B LENSA FADE): kontra-trend BY DESIGN — rs_trend tidak menghukum; dinilai lewat
  lokasi ekstrem + sisa-ruang + tanda kehabisan tenaga. (Obat kasus NEAR 01:35: REJECT 0.97 karena kacamata trend.)
- **trend**: pullback dangkal + volume turun saat koreksi = sah; pullback dalam + volume lawan = tren patah.
- **p6**: fade longgar → bos HARUS lebih galak.
- **scalp**: momentum LANJUTAN — oversold/overbought bukan alasan nolak; REJECT hanya kalau momentum gugur.

### 2c. Rubric 8 dimensi (0–4; timing & likuiditas ×2)
| dimensi | ukuran |
|---|---|
| rs_quality | kualitas setup menyeluruh |
| rs_timing ×2 | freshness — 4 = lemparan awal di pucuk/lembah |
| rs_liquidity ×2 | risiko wick — 4 = SL di balik struktur+wall |
| rs_trend | selaras MTF + money-flow |
| rs_rr | RR dari lokasi entry |
| rs_crowd | funding/OI lawan atau searah |
| rs_vol | volatilitas cocok scalp 5m |
| rs_session | sesi WIB — 4 = LONDON/NEWYORK |

Total = Σ(nilai×bobot)/max → 0-100. **KILL <50 · WAIT 50-64 · SHIP ≥65**.
noul (gugur/flip) rata-rata ≥0.75 → −20 poin.

### 2d. Mekanika keputusan (kode `call_jev`)
```python
conf = Σ p(k dimulai 'CONFIRMED')            # P17: apple-to-apple
# P38-D: argmax REJECT tapi ΣCONFIRMED > p(REJECT) dan ≥0.50 → CONFIRMED(varian terpopuler)
if total < 50:                    → REJECT  [RUBRIC KILL]
elif 50 ≤ total < 65 & CONFIRMED: → REJECT  [RUBRIC WAIT]
if conf < MIN_CONF (55):          → REJECT  [MIN_CONF gate]
```
Resiliensi: 429 retry 3 dtk (max 2); 402 = raise → kandidat dilewati, notif 1×/jam.

---

## 3. EKSEKUTOR (dewa_live.py)

- Slot 5 global, 1 posisi/pair, cooldown 30 mnt/pair, DRY margin $2 → notional $20, lev ×10.
- **WICK-FLIP P16-B**: kalau bos ACC tapi RSI6 realtime >90 (LONG) / <10 (SHORT) → arah dibalik
  (fade pucuk terbukti; kasus NEAR +$0.232 & WLD sim +$0.133).
- SL/TP: NORMAL = SL_PCT env 1.2% + RR regime (chop 1:3, trend 1:4); TIGHT 0.8%/1:2.5;
  WIDE 1.8%/1:4; ATR-SL menaikkan SL minimum; range-guard memaksa WIDE dekat tepi range 6 jam;
  sanity clamp 0.3–3.0% (P36).
- **TRAIL-LOCK P10b** (inti "cuan terus"): hi/lo ekstrem diupdate dari bar closed sejak lahir
  (+ bar forming); LONG: profit ≥0.6% → SL = puncak×(1−0.3%), hanya naik, tidak turun.
  SHORT mirror. → kerugian dibatasi SL awal, kemenangan dikunci.
- MAXHOLD 480/96 bar → exit TIME. PnL net fee maker/taker disimel jujur; rekap harian briefing 07:00 WIB.

---

## 4. FUNNEL NYATA (24 jam 30 Sep)
```
~1.800 skip_dry (103 hint ≥55 dibunuh pra-P38a)  →  ~400-500 ke bos
→ 4 CONFIRMED (0.4-4%)  →  semua win/open via trail-lock
```
Pasca-P39: cooldown persist (303 panggilan duplikat/24 jam hilang), done trim kronologis cap 2000.

## 5. KEGOBLOCKAN KURIR YANG JUJUR (data 23 kandidat 09:35–10:17 WIB)
- **7/23 lokasi-true** (RSI ≤30 / ≥75: AAVE 20.9L, UNI 22.9L, JUP 26.8L, ATOM 29.5L, AAVE 26.9S, DOT 29.7S, TRX 86.9S) — fade engine bekerja sesuai filosofi.
- **16/23 RSI netral (35-60)** — dominan dari scalp/trend engine di pasar mati: tanpa edge lokasi,
  bos bunuh semua (benar). → kandidat kalibrasi berikutnya (butuh ACC user): naikkan syarat
  konteks scalp (bukan gate baru — ketatan biru engine eksisting).
- Wick strength bisa tinggi untuk doji mikro tanpa arah → dir=NONE → gate P38a menahan (benar).

## 6. PETA FILE
| file | baris | peran |
|---|---|---|
| dewa_live.py | 820 | penyelia: loop, gates, eksekusi, trail, state, notif |
| jev_bridge.py | 282 | bos: persona, rubric, keputusan, resiliensi |
| market_snapshot.py | 353 | 13 sensor + wick-hunter + entry-loc |
| smc_engine.py | 335 | MSS/FVG/likuiditas/BTC.D/money-flow + audit P1-P8 |
| dewa_skill.py | 184 | briefing + scalper pack + momentum_class |
| hybrid_rules.py | 182 | trend-pullback + scalp + p6 + dedupe |
| reversion_bot.py | 169 | fade ekstrem + rsi6 (satu-satunya RSI) |
| tg_notify.py | ~260 | format notif TG (entry/exit/lock/briefing) |
| tradfi_session.py | ~150 | gate & force-flat CME |
| v15_grade.py / backtest_v15x_final.py | — | fetch klines + utils (dipakai semua modul) |

## 7. KEJUJURAN TENTANG "100% BENAR"
Tidak ada sistem yang 100%. Sistem ini mengejar 100% lewat:
(1) kurir hanya menyetor lokasi bermutu, (2) bos menolak 99%+ yang kopong,
(3) trail-lock memotong ekor kerugian dan mengunci kemenangan,
(4) setiap patch didahului aknosa + test regresi + bukti live.
WR butuh >63% (breakeven trail-lock) — bucket AT-TURN historis 76.5% adalah jalurnya.
