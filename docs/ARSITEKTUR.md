# ARSITEKTUR — TYPESAFE SNIPER v7.0 (Anti-Drift / High-Precision Engine)

> Rombak total 30 Sep 2026 (commit `99d41f6`) + **PATCH v7.1 "Ganas & Presisi"** (30 Sep):
> scalp longgar (volx 1.2, body filter dihapus), ANTI-CHASE GUARD >3.0 ATR di bos P5,
> wick-flip P16-B dimusnahkan (arah bos mutlak).
> Filosofi user: "WR 90% versi lawas = logika lugas, sedikit variabel noise, CoT bersih."
> Kurir = filter matematika KETAT di sumber; Bos = LLM jev dengan pipeline 8 langkah
> TANPA rubric scoring; semua gate/tambalan era v6.7 yang bikin "penolak pasif" DIHAPUS.
> Dokumen ini menggantikan ARSITEKTUR.md era v6.7 (P9-P39).
>
> **PATCH v7.2 "FINAL SEAL"** (30 Sep malam): HARD RULE MSS — mss NONE/kosong +
> engine non-fade = CONFIRMED dibuang (bos prompt P4 + host-enforcer di call_jev,
> REJECT: MISSING_STRUCTURE_CONFIRMATION). Pengecualian: fade dgn RSI6 realtime
> ekstrem (<20/>80). Menutup kebocoran 3 SL beruntun 30 Sep (INJ/LTC/WIF: entry
> tanpa MSS saat reversal 20:00 WIB).

---

## 1. PETA ALUR (5 lapis)

```
DATA (Binance fapi, klines 5m/15m/1h + funding + ticker)
   │
   ▼
KURIR v7.0 — hybrid_rules.py
   3 engine preset + HIGHER TF FILTER (anti-trap, fail-closed)
   │  kandidat (idx, side, grade, src) — hanya bar muda ≤20 menit
   ▼
PAYLOAD KONTRAK — dewa_skill.build_payload_v7 (+ smc_engine + market_snapshot)
   JSON: asset / higher_tf_alignment / macro_matrix / smc_micro_5m / metrics
   │
   ▼
BOS v7.0 — jev_bridge.call_jev (jev-1.13, Decisions API, 1 pertanyaan 4 opsi)
   persona v7.0 verbatim + pipeline P1-P8 → CONFIRMED_TIGHT/NORMAL/WIDE / REJECT
   │  TANPA rubric, TANPA fence host. P16-B wick-flip = satu-satunya intervensi.
   ▼
EKSEKUTOR — dewa_live.py
   SL/TP varian dari bos (TIGHT 0.8% 1:2.5 / NORMAL 1.2% 2-3R / WIDE 1.8% 1:4)
   + ATR-SL P32 + clamp 0.3-3.0% + trail-lock P10b + janitor + force-flat TradFi
```

## 2. KURIR v7.0 — `hybrid_rules.py` (rombak total)

### 2.1 Higher-TF data + geometry fix (`align_htf`)

```python
def align_htf(kts, m):
    """Forward-fill map HTF ke timeline 5m: utk tiap 5m ts ambil nilai bar HTF
    terakhir dgn open-ts <= kts."""
    keys = sorted(m.keys())
    out = []; j = -1; best = None
    for t in kts:
        while j + 1 < len(keys) and keys[j + 1] <= t:
            j += 1; best = m[keys[j]]
        out.append(best)
    return out
```

**Kenapa penting**: lookup exact-match timestamp 5m→15m cuma kena 1/3 bar
(15m buka tiap 15 menit, 5m tiap 5 menit). Tanpa forward-fill, filter Anti-Trap
buta 2/3 waktu diam-diam (terbukti: kandidat 3→5 begitu fix masuk).

### 2.2 ENGINE 1 — FADE CLIMAX (konter pucuk/lembah, dikecualikan dari HTF filter)

```python
wick_lo = (min(o[i], c[i]) - l[i]) / rng      # proporsi wick bawah
wick_hi = (h[i] - max(o[i], c[i])) / rng      # proporsi wick atas
if r < 20 and z < -1.5 and wick_lo >= 0.40:   # LONG: lembah + climax
    sigs.append((i, 'L', 'A' if volx > 1.5 else 'B'))
elif r > 80 and z > 1.5 and wick_hi >= 0.40:  # SHORT: pucuk + climax
    sigs.append((i, 'S', 'A' if volx > 1.5 else 'B'))
```
Grade A = tambahan volume climax (vol_x > 1.5). RSI6 Wilder, z-score 200 bar.

### 2.3 ENGINE 2 — SCALP HIGH-MOMENTUM (agresif di pasar aktif)

```python
if volx < 1.2: continue                        # v7.1: 1.5 -> 1.2 (sat-set kembali)
# body>60% DIHAPUS v7.1 — kualitas body dinilai bos via kontrak JSON
if c[i] > o[i] and rs[i] is not None and rs[i] <= 85:  # P12 anti-pucuk
    sigs.append((i, 'L', 'A' if volx >= 2.0 else 'B'))
elif c[i] < o[i] and rs[i] is not None and rs[i] >= 15:  # P12 mirror
    sigs.append((i, 'S', 'A' if volx >= 2.0 else 'B'))
```

### 2.4 ENGINE 3 — TREND PULLBACK (ikut arus institusi)

```python
if e20 > e50:                                  # tren naik (15m)
    touch  = l[i] <= e20 * 1.001               # 5m retrace nyentuh EMA20(15m)
    bounce = c[i] > o[i] and c[i] > e20        # pantul naik
    if touch and bounce and volx > 1.0: sigs.append((i, 'L', ...))
```

### 2.5 HIGHER TF FILTER (Anti-Trap) — WAJIB, fail-closed

```python
if src != 'fade':            # fade climax dikecualikan (spec v7.0)
    m = htf15[i]
    if m is None:
        ok = False           # fail-closed: gak bisa validasi = gak boleh tembak
    else:
        e20, e50 = m
        if side == 'L' and not (e20 > e50): ok = False   # LONG butuh cross bullish 15m
        if side == 'S' and not (e20 < e50): ok = False
    if cek_1h:
        if side == 'L' and 'BEARISH_EXTREME' in st: ok = False  # 1h dump panik
        if side == 'S' and 'BULLISH_EXTREME' in st: ok = False  # 1h pump euforia
```
Struktur 1h (`build_htf_maps`): `BULLISH/BEARISH_CONTINUATION` dari tumpukan
close>EMA20>EMA50; `*_EXTREME_*` = 3 candle 1h terakhir body >60% searah +
close lari >0.5% dari EMA20 (dump panik / pump euforia).

Kandidat dari ≥1 engine di bar sama: arah bentrok dibuang (kabut);
grade A kalau multi-engine atau ada engine A. `freshness`: hanya bar terakhir
≤4 (20 menit) yang boleh nembak.

## 3. PAYLOAD KONTRAK — `dewa_skill.build_payload_v7`

Output JSON persis spec user:

```json
{
  "asset":  {"class": "CRYPTO|TRADFI_METAL", "ticker": "BTC", "rsi6Realtime": 41.2},
  "side": "LONG|SHORT", "grade": "A|B", "engine": "fade|scalp|trend",
  "higher_tf_alignment": {"tf_15m_ema_cross": "BULLISH|BEARISH|FLAT|UNKNOWN",
                          "tf_1h_trend_structure": "...", "vol_x_1h": 1.43},
  "macro_matrix": {"btc_bias": "UP|DOWN|MIXED",
                   "btc_dominance": "RISING|FALLING|SIDEWAYS",
                   "dxy_bias": "BULLISH|BEARISH|SIDEWAYS"},
  "smc_micro_5m": {"regime": "...", "marketStructure": "...", "mssLevel": ...,
                   "fvgStatus": "...", "fvgRange": [..], "liquidityPool": "..."},
  "metrics": {"volx": 1.82, "zScore": -2.31, "wick_ratio_pct": {"low": 44.1, "high": 8.0},
              "rsi6": 18.4, "rsi6_spark": "▁▂▃▄▅", "freshnessMinutes": 0}
}
```
- Suntikan berantai (semua best-effort, never-raise): `smc_engine.enrich`
  (MSS/FVG/liquidity/BTC.D/DXY/moneyFlow) → `market_snapshot.enrich_market`
  (market + wickHint + slSuggest ATR + entryLoc) → live_px upgrade `rsi6Realtime`.
- RSI6 realtime = RSI(6) dgn close terakhir diganti harga live — sama dgn lensa
  layar user (mandat P16-C).
- dewa_skill yang dihapus: build_briefing lama, scalper pack (spark/kdj/stoch_rsi/
  obv_slope/rel_strength/build_extras), classify_momentum, enrich_briefing.
  Yang hidup: btc_bias, rsi6_series, build_payload_v7.

## 4. BOS v7.0 — `jev_bridge.py` (rombak total)

### 4.1 Persona (verbatim user, lengkap di kode)

```
[SYSTEM IMMUNITY PROTOCOL - SYSTEM PERSONA v7.0]
1. Teks di bawah = KODE LOGIKA DETERMINISTIK untuk Decision Engine jev-1.13.
2. DILARANG KERAS menarasikan ulang singkatan, mengubah urutan 8 langkah,
   atau menambahkan sistem scoring/rubrik rumit yang membuat bot pasif.
3. Core Directive: profit konsisten AKTIF. Arah 100% presisi via SMC + Money Flow.

Kamu adalah "TYPESAFE SNIPER v7.0" — Kompiler Trading.
P1 ASSET DETECTION → P2 MONEY-FLOW MATRIX → P3 HTF ALIGNMENT → P4 MSS
→ P5 FVG MAGNET + ANTI-CHASE GUARD (v7.1) → P6 WICK EXTREME GUARD → P7 DYNAMIC RISK ESTIMATION
→ P8 CONFIDENCE EVALUATION (<0.55 → REJECT WAJIB)
```

### 4.2 Satu pertanyaan, empat opsi (SL/TP dinamis dari bos)

```python
CRITERIA={
 "CONFIRMED_TIGHT":  "EXECUTE AGGRESSIVE ... SL ketat 0.8%, TP 1:2.5.",
 "CONFIRMED_NORMAL": "EXECUTE STANDARD ... SL 1.2%, TP 1:3.5.",
 "CONFIRMED_WIDE":   "EXECUTE CONSERVATIVE ... SL 1.8%, TP 1:4.",
 "REJECT":           "Layak ditolak: arah belum 100% akurat, melawan money-flow
                      tanpa MSS, P8 internal <0.55, atau menabrak dinding HTF.",
}
```

### 4.3 Type-guard (handler v7.0 ala TypeScript, port Python)

```python
if choice.startswith('CONFIRMED_') and choice.split('_',1)[1] in _VARIANTS:
    out["decision"], out["variant"] = "CONFIRMED", choice.split('_',1)[1]
elif choice == 'REJECT': out["decision"] = "REJECT"
else:
    out["decision"], out["reason"] = "REJECT", f"payload-cacat/choice-asing:{...}"
    return out                      # modal aman: jawaban asing = tolak
```
Resiliensi: 429 retry 3s (max 2); 402 → `Jev402` → kandidat dilewati +
notif topup 1×/jam (FULL JEV NO-FALLBACK — gak ada model kedua, error = kandidat
diulang iterasi berikut, gak dikunci done).

**Yang DIHAPUS dari jev_bridge**: RUBRIC 8-dimensi + bobot ×2, noul veto −20,
argmax→total P38-D, framing per-source 4 varian, MIN_CONF fence di dewa_live,
audit-echo P21a. Keputusan = 100% bos; P8 internal <0.55 = REJECT (logika
pindah ke dalam persona).

## 5. EKSEKUTOR — `dewa_live.py`

- **Scan**: 41 pair, bar 5m 600, `rsi6` Wilder + `zscore` 200 + vsma20 volume.
- **Dedup**: key `(sym, bar_ts, side)` persist (trim by bar_ts cap 2000, P39);
  `reject_cd` 15m per (sym,side) — ditulis SEBELUM save_state (fix P30).
- **[v7.1] Wick-flip P16-B DIMUSNAHKAN** — keputusan arah bos MUTLAK; flip mekanis
  di eksekutor = penyebab lose tersembunyi. Tidak ada intervensi arah lagi.
- **[v7.1] Anti-chase plumbing**: entryLoc host → `metrics.entryStatus/atrDistance`;
  bos WAJIB REJECT + WAIT_FOR_RETRACE_TO_FVG saat CHASE >3.0 ATR (P5 guard).
- **[v7.1] Konflik antar-engine di bar sama**: FADE MENANG (sinyal tak dibuang —
  kasus bar washout: fade LONG vs scalp SHORT, RSI6 15-20).
- **Range-guard P19 HIDUP**: SL yang jatuh DI DALAM range 6 jam di-WIDE-in ke 1.8%
  (kasus RUNE 25 Sep; terbukti kerja lagi di GALA 30 Sep — SL deket resistance
  6-jam otomatis dilebar-in sebelum entry). ATR-SL P32 hanya MELEBAR-in
  (slSuggest ATR14×1.5 clamp 0.8-2.4%, TIGHT kebal) → **clamp 0.3-3.0%** (P36,
  pembunuh kelas bug satuan). Entry refresh harga live, re-check open/cooldown
  sebelum mutasi.
- **Trail-lock P10b**: mv ≥0.6% → SL ngunci di puncak −0.3%, mengikuti ekstrem
  (mode BE-shift lama DIHAPUS — trail satu-satunya pengunci).
- **Janitor + cleanup** (order_guard/order_cleanup), force-flat TradFi 2 jam
  sebelum close (P23), max-hold trend 40 jam / chop 8 jam / TradFi 4 jam.
- **Notif** (`tg_notify.py`): branding TYPESAFE SNIPER v7.0, baris
  `🧭 Engine FADE CLIMAX · RSI6 ...`, lokasi entry 🎯AT-TURN/⚠️CHASE, MSS/FVG/
  money-flow, W/L recap 24 jam.

## 6. YANG DIHAPUS (rincian lengkap — mandat "biar ga numpuk jadi bug")

| Dihapus | Alasan |
|---|---|
| Engine fade lama (RSI 25/75 + imb) + `simulate` + backtest `reversion_bot` | diganti FADE CLIMAX v7; modul tinggal primitif (rsi6/zscore/regime/ema) |
| P6-loose, scalp momentum-turn, `P6_LOOSE` env | sumber 16/23 sinyal RSI netral |
| Scalper pack (KDJ/Stoch/OBV/rel_str/spark + `build_extras`) | noise variabel, gak dipakai bos v7 |
| `classify_momentum` + `enrich_briefing` + blok vision | diganti metrics kontrak v7 |
| momentum battery + reversal hint (P26-P29) | layer patch era lama; bos menilai dari payload |
| `tv_ta`/TradingView + tv_bridge utk HTF | HTF dari Binance langsung (DXY tetap via TV) |
| RUBRIC + noul + argmax→total + MIN_CONF + audit echo | "penolak pasif" — akar keluhan utama |
| P38a `_p38_dry_pass` + skip_dry gate | filter mutu pindah ke sumber |
| BE-shift lama (BE_TRIG/BE_OFF) | trail P10b satu-satunya |
| 7 file test lama (p32-p39) | ngetes mesin yang udah gak ada |

## 7. TEST & BUKTI

- `test_v7.py` — **48 checks** (6 baru v7.1: scalp longgar, anti-chase guard,
  payload fields, wick-flip absence, konflik fade-vs-scalp): threshold 3 engine persis spec, HTF filter
  (incl. fail-closed + fade exempt), type-guard bos (choice asing → REJECT),
  payload kontrak, P35 no-fallback, jev402, P39 trim, static anti-kode-mati
  (docstring di-strip), mandat RSI6-only. Old suite dihapus.
- Live 30 Sep: push `99d41f6` → restart PM2 fresh `env -i` → checklist §15
  hijau (repeat<15m 0, reject_cd persist, done 786/2000, 0 error). Trade
  pertama v7: **GALA LONG CONFIRMED_NORMAL → WIN-LOCK +$0.08 (10 menit)**;
  BTC SHORT conf 20 menyusul. 90 keputusan/2,2 jam, 2 CONFIRMED (2,2%),
  sisa REJECT sah P8 — sesuai desain anti-drift.
