# DEWA Bot — V15 Evolution (Binance USDⓈ-M Futures 5m)

Bot trading futures Binance TF 5m: **algoritma matematika = kurir** sinyal grade A/B →
**1 LLM agent ("SNIPER LIKUIDITAS") = bos** final entry. Mode default **DRY RUN**
(eksekusi virtual, tanpa API key Binance, tanpa risiko duit).

Fitur: notifikasi Telegram per entry/exit (win/lose + saldo net + reasoning bos LLM),
cleanup otomatis SL/TP nyantol, morning briefing harian.

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
Isi:
```bash
LLM_BASE_URL=https://<gateway-openai-compatible>/v1   # endpoint OpenAI-compatible
LLM_API_KEY=<key gateway lo>
LLM_MODEL=auto

# Telegram notifikasi (WAJIB utk notif & briefing):
TG_BOT_TOKEN=<token dari BotFather>
TG_CHAT_ID=<chat id lo>

# Hanya untuk mode --live:
BINANCE_API_KEY=
BINANCE_API_SECRET=
```

### 5. Tes cepat (dry run 1 iterasi)
```bash
set -a; source .env; set +a
python3 dewa_live.py --once
```
Output sukses: JSON `{"realized": [...], "candidates": N, "confirmed": N, "open_now": N}`.
Kalau lo coba sambil ada sinyal & Telegram aktif → notif entry masuk ke chat lo.

### 6. Jalankan dry run terus-menerus
```bash
# Loop scan tiap 60 detik:
set -a; source .env; set +a
nohup python3 dewa_live.py > dewa_run.log 2>&1 &

# Cek posisi/log:
tail -f dewa_live_log.jsonl
```

### 7. Morning briefing otomatis (07:00 WIB)
```bash
crontab -e
# tambahkan:
0 23 * * * cd /path/ke/dewa-bot && set -a && . ./.env && set +a && python3 dewa_live.py --report >> briefing.log 2>&1
```
(23:00 UTC = 07:00 WIB. `--report` mengirim briefing ke Telegram + stdout.)

### 8. (Nanti, kalau yakin) Mode LIVE
1. Binance → API Management → Create API → **enable Futures**, **JANGAN enable Withdraw**,
   batasi IP ke server lo.
2. Isi `BINANCE_API_KEY` & `BINANCE_API_SECRET` di `.env`.
3. `python3 dewa_live.py --live`
4. SL/TP dipasang sebagai conditional closePosition orders + **janitor** memverifikasi
   tiap 5 detik dan memasang ulang bila gagal/rate-limited. Setelah close, leftover
   orders dibersihkan & diverifikasi (`order_cleanup.py`).

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
      aturan mati: volume kering/funding searah ekstrem/ragu = REJECT)
  → RISK: max 5 posisi global, 1 posisi/pair
  → EKSEKUSI: entry open candle berikutnya, margin $2, lev 10x,
      SL max(0.35%, 0.4%), TP = 3×SL (RR 3:1), BE-shift +0.1% → entry+0.06%,
      max hold 480 bar
  → JANITOR: verifikasi SL/TP tiap 5 detik (live), cleanup setelah close
  → TELEGRAM: notif entry/exit (dengan reasoning bos), briefing pagi
```

## FILE

| File | Peran |
|---|---|
| `dewa_live.py` | Mesin utama live/dry-run + report + briefing |
| `dewa_skill.py` | System prompt skill dewa (inject ke bos LLM) |
| `dewa_dryrun.py` | Dry run replay historis (LLM beneran dipanggil) |
| `order_guard.py` | Janitor SL/TP + max posisi global |
| `order_cleanup.py` | Bersihkan SL/TP nyantol setelah posisi close |
| `tg_notify.py` | Notifikasi Telegram (entry/exit/briefing) |
| `reversion_bot.py` | Kurir: indikator + generator sinyal fade-ekstrem |
| `reversion_dewa.py` | Backtest regime-adaptif (trend/chop sniper) |
| `dewa_v3.py` | Backtest final: max 5 posisi, laporan per minggu/hari |
| `tv_bridge.js` | Bridge TradingView (EMA/RSI multi-TF; metals via OANDA) |

## HASIL BACKTEST (jujur)

9 engine, ~60.000 trade simulasi, IS/OOS terpisah, fee taker 0.05%/sisi ×10x:
- V15 StochRSI cross original: **-$70.50** (3.825 trades)
- Fade-ekstrem + rulebook ketat (engine ini): **-$0.67** (349 trades) — dekat breakeven
- **Tidak ada klaim profit.** Dry run 2 minggu adalah ujian sebenarnya.

## DISCLAIMER

Edukasi & riset. Bukan saran finansial. Futures leverage tinggi dapat menghapus
modal. Gunakan dana dingin. DRY RUN dulu — jangan langsung LIVE.
