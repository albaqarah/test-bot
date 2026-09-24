# DEWA Bot — V15 Evolution (Binance USDⓈ-M Futures 5m)

Bot trading futures Binance TF 5m: **algoritma matematika = kurir** sinyal grade A/B →
**1 LLM agent ("SNIPER LIKUIDITAS") = bos** final entry. Mode default **DRY RUN**
(eksekusi virtual, tanpa API key Binance, tanpa risiko duit).

Fitur: notifikasi Telegram per entry/exit (win/lose + saldo net + reasoning bos LLM),
cleanup otomatis SL/TP nyantol, morning briefing harian, **panel tuning .env**,
**switch MODE dry/live**, **auto-restart supervisor**, anti-hang & anti-race.

---


## CHANGELOG v6.3 (24 Sep malam) - TRADFI GATE + NOTIF v15 STYLE

### P14: TradFi Session Gate (CME hours)
- Entry XAU/XAG/XPT/PAXG HANYA saat session OPEN (unit test 10/10 skenario)
- CLOSED: weekend (Fri >=17:00 ET s/d Sun 18:00 ET) + daily break 17:00-18:00 ET
- Gate di kurir SEBELUM bos LLM = nol panggilan API saat market tutup
- `skip_tradfi_closed` di log; label session tampil di notif start & briefing

### Notif gaya v15 (isi sistem v6.2)
- START: BOT START · DEWA SNIPER v6.2 + panel Mode/Ekuitas/Margin/Slot/TP-SL/BE-TRAIL/TradFi/Bos
- ENTRY: harga, notional, TP/SL %, varian bos, regime, momentum_class+RSI6, slot, rekap 24h
- TRAIL LOCK: notif khusus saat SL trailing mengunci profit (puncak − 0.3%)
- CLOSED: bar ROI, Entry→Exit (harga eksekusi asli), Gross/Fee/NET terpisah, rekap 24 jam, cooldown
- MORNING BRIEFING: bar winrate ▰▱, PF, Gross/Fee/NET, leaderboard best/worst, regime, TradFi, bos
- Klasifikasi W/L jujur: exit rata (LOCK/BE) tidak dihitung lose

### Audit full sebelum push
- Compile 11 module OK; import chain OK; konstanta panel OK
- Smoke 41 pair: 995 sinyal valid, vision enrich 995/995, 0 tuple rusak
- Live: err 0, 1 proses, gate hemat-api tercatat, notif pipeline terkirim

## CHANGELOG v6.2 (24 Sep) - JEV BOS + TRAILING PROFIT LOCK + VISION PACK

### Bos LLM: JEV (TypeSafe jev-1.13)
- **BOS_PROVIDER=jev** di .env — keputusan typed via OpenRouter Decisions API: 0.3-0.6 dtk, probabilitas per opsi, $0.0000165/keputusan
- Failover otomatis ke lightvela kalau jev error (`jev_fallback` di log)
- **P11**: bos pilih varian eksekusi SL/TP per-sinyal: TIGHT (SL 0.8% TP 1:2.5) / NORMAL / WIDE (SL 1.8% TP 1:4, anti-wick) — engine lama tetap fallback

### P10b: Trailing Profit Lock (breakeven asli)
- SL diam di posisi awal sampai profit >= TRAIL_ACT (0.6%) → kunci puncak − TRAIL_DIST (0.3%) → SL ngikut naik/turun sampai TP
- Kena balik = **WIN-LOCK** (profit terkunci di atas fee), bukan BE rata -$0.01
- Toggle `TRAIL=on/off` di .env; BE lama tinggal rollback path (dengan fix arah SHORT + filter bar-born)
- Audit exit lengkap di log: exit_px/sl/entry/hi/lo

### P12: Anti-pucuk guard
- Breakout LONG dilarang saat RSI(6) > 85; breakout SHORT dilarang saat RSI(6) < 15 (kasus RUNE 10:00 WIB: breakout beli di RSI6 97)

### P13: Vision Pack (bos & kurir bisa "lihat")
- Briefing bos + `vision`: RSI(6) realtime + sparkline 12 bar, momentum_class (wick_extreme / momentum_fallback / mean_reversion / breakout / kering), last bar OHLCV
- Kurir gate: momen `kering` (volx<1.0) dibuang sebelum bos (hemat API)
- Bukti: replay RUNE 10:00 → dulu CONFIRMED conf 40 (boncos), kini REJECT conf 61 dgn konteks pucuk terbaca

### Infra & notif
- Gate hemat-api: posisi 5/5 → kurir TIDAK nanya bos (notif cuma di log bot, bukan TG); sinyal tidak dikunci permanen
- Notif exit: "Exit harga" = harga eksekusi asli (singkron app), PnL selalu bersih fee taker 0.05%×2
- pm2: dump dibenerin (insiden registry kosong 04:04-06:51 WIB)

## CHANGELOG PATCH v6.1 (23 Sep malam) - HOTFIX

### P9 CRITICAL FIX - Side inversion
- BUG: kurir ngirim side 'L'/'S' tapi jalur mutasi cek 'LONG'/'SHORT' -> SEMUA posisi LONG dapat
  SL/TP TERBALIK (SL di atas, TP di bawah) + arah PnL salah. Kasus nyata: BCH LONG 21:51 WIB
  entry 330.19, SL 334.15 (atas!), TP 318.30 (bawah!) -> profit +3.18% dicatat -$0.26.
- FIX: normalisasi side di satu titik sebelum mutasi; unit test orientasi LONG/SHORT wajib lulus.
- BONUS BUG: branch LIVE memakai variabel posisi SEBELUMNYA (dipakai sebelum didefinisikan) -
  fatal saat MODE=live. Direstrukturisasi: hitung entry/side/SL/TP dulu -> baru cabang LIVE/dry.
- Entry refresh: harga live fapi saat CONFIRMED (bukan open-candle basi 2.8%).
- Ledger dikoreksi: -$1.08 -> -$0.18 (audit trail di state).

### P1 - Cooldown di titik mutasi
- Re-check cooldown tepat sebelum open (dulu cuma saat scan) - anti re-entry 100 detik pasca-SL.

### P7 - Briefing source-aware
- Kandidat scalper dibingkai "MOMENTUM LANJUTAN" ke bos LLM: oversold/overbought BUKAN alasan
  nolak (itu tandanya gerakan kuat). Bos nilai konfirmasi lanjutan, bukan reversal fade.

### P8 - Scalper rev (indikator layar scalper)
- Trigger tambahan: RSI(6) belok dari >80/<20 (persis lensa Binance app user).
- OBV jadi soft-veto (nolak hanya jika melawan >3x avg vol) - OBV hard-gate lama membunuh
  SHORT pucuk valid (OBV selalu positif habis rally = kontradiktif dengan momentum lanjutan).
- Replay bukti: pucuk BTC 23 Sep 20:44 WIB (RSI6 84) kini tertangkap - SHORT @85.783 jam 20:35.

## CHANGELOG PATCH v6 (23 Sep 2026)

### P5 - Kurir Scalper Momentum (JALUR BARU, default ON)
- Masalah: kurir lama cuma 1 jalur (fade ekstrem 3-gate: RSI>75 + z>1.5 + wick) -> blind 94% momen scalping
  (bedah 9,5 jam: 17 fade lolos vs 259 momen momentum, 39 di antaranya gerak >=2%)
- Generator baru `gen_scalp` (hybrid_rules.py): stoch_rsi belok dari ekstrem (>80 turun = SHORT / <20 naik = LONG)
  + breakout (volx>2.5, body>60%) + konfirmasi OBV 10-bar searah + volx>=1.2
- Backtest 30 hari (41 pair, ekonomi bot asli): 11.528 trade, avg +$0.117, PnL virtual +$1.354
- FRESHNESS GATE: sinyal scalp hanya dikirim ke bos LLM jika umur <=4 bar (20 menit) - sinyal tua bikin
  backlog LLM 30-45 detik/keputusan (lightvela reasoning burn) dan scalping gak nunggu 90 menit

### P6 - Fade Longgar (TOGGLE, default OFF)
- `gen_loose_fade`: varian A (z>=3.0 bypass wick-gate) + varian B (RSI 70/30 + z>2.5)
- Backtest 30 hari: A 1.635 trade avg +$0.076 | B 1.008 trade avg +$0.132 (keduanya expectancy positif)
- AKTIFKAN: .env `P6_LOOSE=on` -> restart. ROLLBACK: `P6_LOOSE=off` (tanpa sentuh kode)

### Skill bos v6 (dewa_skill.py)
- Paket analisis baru untuk briefing bos LLM: `chart` (sparkline 24-candle ASCII), `kdj`, `stoch_rsi`,
  `obv_slope`, `btc_bias` (EMA20/50 BTC 1h), `rel_str_24h` (kekuatan alt vs BTC, proxy dominance)
- Aturan scalper momentum 4/6 konfirmasi: boleh entry walau RSI gak ekstrem, grade B di RANGE boleh lewat
- Anti-jebakan-wick: bos wajib pikirkan SL di balik struktur + TP di swing berikutnya

### FIX BE race + pm2 satu penulis state
- BUG: cron hourly `--once` = iterator kedua, timpa state pm2 (be_moved True hilang -> 4/11 SL full padahal
  sempet profit; kasus UNI trig 24 menit sebelum SL). Cron DI-PAUSE permanen - pm2 = satu-satunya penulis
- Bukti fix: 4/4 posisi BE exit -$0.01 (FIL, LDO, ATOM, ENA) - sebelumnya -$0.26 per SL
- Migrasi supervisor bash -> pm2 (auto-boot systemd, restart-delay 5s, kill-switch exit 99 tetap)

### Lain-lain
- llm_err tidak lagi membunuh kandidat permanen (done.discard -> retry iterasi berikutnya)
- Boot-lock check + re-check pre-mutasi (anti dobel proses / dobel entry)
- Parser .env strip komentar inline + config echo di startup notif

## CHANGELOG PATCH v5 (22 Sep 2026)

| Patch | Isi |
|---|---|
| **MODE dry/live via .env** | `MODE=dry` ↔ `MODE=live` di `.env` + restart = ganti mode. LIVE = market order beneran + SL/TP conditional nyata + janitor. Fallback aman: MODE=live tanpa API key → auto-DRY + warning `[SAFETY]` |
| **Panel tuning .env** | Semua parameter kunci dibaca dari .env: MARGIN_USD, LEVERAGE, SL_PCT, TP_RR_TREND, TP_RR_CHOP, BE_TRIG, BE_OFF, MAXHOLD_TREND/CHOP, COOLDOWN_MIN, SCAN_SEC. Ubah angka → restart → berlaku. Gak perlu sentuh kode |
| **CHOP SNIPER MODE** | Regime RANGE = TP 1:3 (RR dinamis per regime), MAXHOLD 96 bar (8 jam), grade A wajib. TREND = TP 1:4, hold 40 jam. Regime disimpan di posisi + tampil di notif |
| **SL anti-wick** | SL proporsional dari entry (kini 1.2%, riwayat: 0.4% → 0.8% → 1.2%). Coin sub-cent gak lagi dapet SL mustahil (GALA 167% bug fixed) |
| **File-lock anti-race** | `fcntl` lock: cuma 1 proses boleh mutasi state. Watchdog/cron jadi fallback-only (`skipped: locked_by_other_process`) |
| **Done-set dedup** | Kandidat unik per (pair, bar, side) — zombie repeat 17-40× fixed |
| **Cooldown 30 menit/pair** | Anti re-entry langsung setelah exit (config: COOLDOWN_MIN) |
| **Anti-hang lengkap** | Timeout 8s semua fetch + kill-switch timer (exit 99) + `dewa_supervisor.sh` auto-restart 5s. Postmortem: fundingRate urlopen tanpa timeout = TCP nyangkut 7 jam |
| **LLM anti-reasoning-burn** | Instruksi "langsung JSON" — reasoning model gak lagi makan max_tokens buat thinking (no_json_in_response massal fixed); retry 2× + backoff |
| **save_state per keputusan** | Kill di tengah iterasi gak lagi bikin keputusan hilang/diulang |
| **tg.send retry 3×** | Notif gak hilang senyap (kasus TRX SL tanpa notif); kegagalan dicatat |
| **last_reason dari CONFIRMED** | Notif exit nunjukin reasoning bos saat entry (bukan reject terakhir / llm_err) |
| **Startup notif + echo config** | "🤖 BOT ONLINE" tiap restart + baris config aktif: SL/TP/margin/BE — anti silent-drift |
| **BE-shift (breakeven)** | Profit ≥ 0.1% → SL digeser ke entry+0.06% (nutup fee). Selalu aktif tiap iterasi |

---

## INSTALL DARI AWAL SAMPAI AKHIR

### 0. Prasyarat
- VPS/server Linux (Ubuntu 20.04+) — 1 vCPU / 1GB RAM cukup
- Python 3.9+
- Node.js ≥ 14 (`apt install nodejs npm` atau nvm)
- Akun Telegram (buat bot sendiri, gratis)
- (Opsional, untuk mode LIVE) API key Binance Futures

### 1. Clone repo
```bash
git clone https://github.com/albaqarah/test-bot.git dewa-bot
cd dewa-bot
```

### 2. Install dependensi
```bash
# Python: hanya stdlib — tidak ada pip install yang wajib.
# Node (untuk data TradingView multi-TF):
cd /tmp
git clone --depth 1 https://github.com/Mathieu2301/TradingView-API tvapi
cd tvapi && npm install
```
> tv_bridge.js membaca dari `/tmp/tvapi/main.js`. Kalau clone ke lokasi lain,
> edit path di bagian atas `tv_bridge.js` / `dewa_live.py` (`subprocess.run`).

### 3. Buat bot Telegram + ambil chat ID
1. Chat **@BotFather** di Telegram → `/newbot` → simpan **bot token**.
2. Kirim 1 pesan apa pun ke bot baru lo.
3. Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` → cari `"chat":{"id": ...}`.
   Itu **chat ID** lo.

### 4. Konfigurasi environment
```bash
cp .env.example .env
nano .env
```
```bash
# [KONEKSI]
LLM_BASE_URL=https://<gateway-openai-compatible>/v1
LLM_API_KEY=<key gateway lo>
LLM_MODEL=auto

# Telegram notif (WAJIB):
TG_BOT_TOKEN=<token BotFather>
TG_CHAT_ID=<chat id lo>

# Binance — kosong = DRY RUN. Isi + MODE=live = order beneran:
BINANCE_API_KEY=
BINANCE_API_SECRET=
MODE=dry            # 'live' = eksekusi nyata (butuh key Binance)

# ===== TUNING BOT (ubah angka → restart) =====
MARGIN_USD=2          # margin per posisi ($)
LEVERAGE=10           # leverage
SL_PCT=0.012          # SL = 1.2% dari entry (anti-wick)
TP_RR_TREND=4.0       # TP 1:4 saat regime TREND
TP_RR_CHOP=3.0        # TP 1:3 saat regime RANGE/chop
BE_TRIG=0.0010        # shift BE kalau profit ≥ 0.1%
BE_OFF=0.0006         # BE = entry ± 0.06% (nutup fee)
MAXHOLD_TREND=480     # max hold trend (480 bar = 40 jam)
MAXHOLD_CHOP=96       # max hold chop (96 bar = 8 jam)
COOLDOWN_MIN=30       # anti re-entry pair baru exit (menit)
SCAN_SEC=60           # jeda antar scan idle (detik)
```
> ⚠️ Jangan taruh komentar di belakang angka? Boleh — parser nge-strip `#` otomatis.

### 5. Tes cepat (dry run 1 iterasi)
```bash
python3 dewa_live.py --once
```
Output sukses: JSON `{"realized": [...], "candidates": N, "confirmed": N, "open_now": N}`.
Kalau sinyal muncul & Telegram aktif → notif entry masuk.

### 6. Jalankan produksi (supervisor auto-restart)
```bash
setsid nohup ./dewa_supervisor.sh > /dev/null 2>&1 &
# supervisor: while-true, restart 5 detik setelah proses mati/hang (kill-switch exit 99)
# cek:
tail -f dewa_loop.log dewa_supervisor.log
```
Alternatif manual: `nohup python3 dewa_live.py > dewa_run.log 2>&1 &`

### 7. Morning briefing otomatis (07:00 WIB)
```bash
crontab -e
# tambahkan:
0 23 * * * cd /path/ke/dewa-bot && set -a && . ./.env && set +a && python3 dewa_live.py --report >> briefing.log 2>&1
```
(23:00 UTC = 07:00 WIB. `--report` mengirim briefing ke Telegram + stdout.)

### 8. Ganti mode DRY ↔ LIVE
```bash
nano .env        # MODE=dry → MODE=live (dan isi key Binance)
pkill -f dewa_live.py   # supervisor auto-restart dgn config baru
```
- LIVE: entry = market order nyata, SL/TP = conditional closePosition orders nyata
- **Janitor** verifikasi tiap 5 detik + pasang ulang bila gagal/rate-limited
  (SL/TP TIDAK dibiarkan kosong — dikejar sampai terverifikasi terpasang)
- Setelah close, leftover orders dibersihkan (`order_cleanup.py`)
- Fallback aman: MODE=live tanpa API key → bot tetap hidup sebagai DRY + `[SAFETY]` warning
- Notif LIVE ditandai 🟢 MODE LIVE

---

## ARSITEKTUR

```
Data (Binance klines 5m/1h + funding + TradingView multi-TF)
  → KURIR: RSI(14) Wilder + z-score(200) + wick imbalance + volume SMA20
      LONG  : RSI<25  + z<-1.5 + wick bawah ≥0.25  (+vol>1.5x = grade A)
      SHORT : RSI>75  + z>1.5  + wick atas  ≥0.25  (+vol>1.5x = grade A)
      Grade C dibuang — tidak pernah sampai ke LLM
  → BRIEFING JSON ke LLM bos (skill: climax vs drift, absorption wick,
      anti-falling-knife, funding=map kerumunan, konfluensi 5m/15m/1h,
      aturan mati: volume kering/funding searah ekstrem/ragu = REJECT;
      CHOP SNIPER: regime RANGE = climax dua arah, grade A wajib)
  → RISK: max 5 posisi global, 1 posisi/pair, cooldown 30 menit/pair,
      file-lock single-writer (anti race condition multi-proses)
  → EKSEKUSI: entry open candle berikutnya, margin $2, lev 10x (semua via .env),
      SL = 1.2% entry (anti-wick), TP = RR dinamis (1:4 trend / 1:3 chop),
      BE-shift +0.1% → entry±0.06%, max hold 40 jam (trend) / 8 jam (chop)
  → JANITOR: verifikasi SL/TP tiap 5 detik (live), cleanup setelah close
  → TELEGRAM: notif entry/exit (reasoning bos saat entry), briefing pagi,
      startup "BOT ONLINE" + echo config aktif
  → RESILIENCE: fetch timeout 8s, kill-switch timer exit 99, supervisor
      auto-restart 5s, save_state per keputusan, tg.send retry 3×
```

## FILE

| File | Peran |
|---|---|
| `dewa_live.py` | Mesin utama live/dry-run + panel tuning loader + report + briefing |
| `dewa_skill.py` | System prompt skill dewa (inject ke bos LLM) + instruksi CHOP SNIPER |
| `order_guard.py` | Janitor SL/TP + max posisi global + eksekusi order LIVE |
| `order_cleanup.py` | Bersihkan SL/TP nyantol setelah posisi close |
| `tg_notify.py` | Notifikasi Telegram (entry/exit/briefing, RR dinamis, label CHOP/TREND) |
| `reversion_bot.py` | Kurir: indikator + generator sinyal fade-ekstrem |
| `hybrid_rules.py` | Kurir hybrid: fade-ekstrem + trend pullback |
| `dewa_supervisor.sh` | Auto-restart loop (while-true, 5 detik) |
| `position_watchdog.sh` | Watchdog SL/TP fallback-only (respect file-lock) |
| `dewa_dryrun.py` | Dry run replay historis (LLM beneran dipanggil) |
| `tv_bridge.js` | Bridge TradingView (EMA/RSI multi-TF; metals via OANDA) |

## HASIL BACKTEST (jujur)

**Riwayat engine lama** (9 engine, ~60.000 trade, IS/OOS terpisah, fee taker 0.05%/sisi ×10x):
- V15 StochRSI cross original: **-$70.50** (3.825 trades)
- Fade-ekstrem + rulebook ketat: **-$0.67** (349 trades) — dekat breakeven

**Backtest 30 hari engine v6** (41 pair USDⓈ-M, 5m, ekonomi bot asli: SL 1.2% = -$0.26,
TP 4R trend = +$0.94, TP 3R chop = +$0.68, BE = -$0.01, regime 1h EMA20/50):

| Kurir | Trade | TP | SL | BE | PnL virtual | Avg/trade |
|---|---|---|---|---|---|---|
| FADE asli (v5) | 1.122 | 169 | 51 | 902 | **+$121** | +$0.108 |
| P6-A fade longgar (z≥3 bypass wick) | 1.635 | 192 | 91 | 1.351 | +$124 | +$0.076 |
| P6-B fade longgar (RSI 70 + z>2.5) | 1.008 | 175 | 36 | 797 | **+$133** | +$0.132 |
| P5 SCALPER momentum | 11.528 | 1.764 | 337 | 9.388 | **+$1.354** | +$0.117 |
| Semua gabung (P5+P6) | 15.293 | 2.300 | 515 | 12.438 | +$1.732 | +$0.113 |

**Catatan jujur:**
- Simulasi ideal: belum termasuk penolakan bos LLM (~75% reject), batas max 5 posisi global,
  slippage fill, dan delay keputusan LLM. Hasil real pasti lebih kecil - angka dipakai untuk
  BANDINGKANT Expectancy antar-kurir, bukan proyeksi cuan.
- P6 default OFF (toggle .env `P6_LOOSE`) sampai data live membuktikan.
- **Tidak ada klaim winrate/profit.** Dry run adalah ujian sebenarnya.

## HASIL DRY RUN LIVE (ledger resmi, per 23 Sep 2026)

- Day-2 hybrid+LLM: **+$0.46** (3W/1L: WLD/ORDI/SUI TP, TRX SL)
- UNIUSDT SHORT grade B: **+$0.22** (conf 74, climax z5.2 vol2.5x RSI90, TP 6 detik)
- Acc rate bos LLM ~43%; kandidat kurir ~0.4-1% candle — idle itu normal

## DISCLAIMER

Edukasi & riset. Bukan saran finansial. Futures leverage tinggi dapat menghapus
modal. Gunakan dana dingin. DRY RUN dulu — jangan langsung LIVE.
