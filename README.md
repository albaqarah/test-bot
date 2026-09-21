# DEWA Bot — V15 Evolution (Binance USDⓈ-M Futures 5m)

Bot trading futures Binance TF 5m: algoritma matematika sebagai **kurir** sinyal
grade A/B → **1 LLM agent** ("SNIPER LIKUIDITAS") sebagai bos final entry.
Mode default DRY RUN (eksekusi virtual, tanpa API key Binance).

## Arsitektur

```
Data (Binance klines + funding + TradingView multi-TF)
  → Kurir matematika (RSI Wilder + z-score 200 + wick imbalance + volume climax)
  → Grade A/B (C dibuang, ~0.4% candle lolos)
  → Briefing JSON → LLM bos (skill microstructure: climax, absorption wick,
    anti-falling-knife, funding map, multi-TF confluence, aturan mati)
  → Risk gate (max 5 posisi global, 1 posisi/pair)
  → Eksekusi ($2 margin, 10x, SL max(0.35%,0.4%), TP 3R, BE-shift +0.1%→+0.06%)
  → Janitor SL/TP (verifikasi tiap 5s, retry, tidak pernah force-close)
```

## File

| File | Peran |
|---|---|
| `dewa_live.py` | Mesin utama live/dry-run + laporan harian |
| `dewa_skill.py` | System prompt skill dewa (inject ke LLM bos) |
| `dewa_dryrun.py` | Dry run replay historis (LLM beneran dipanggil) |
| `order_guard.py` | Janitor SL/TP + max posisi global |
| `reversion_bot.py` | Kurir: indikator + generator sinyal fade-ekstrem |
| `reversion_dewa.py` | Backtest regime-adaptif (trend/chop sniper) |
| `dewa_v3.py` | Backtest final: max 5 posisi, laporan per minggu/hari |
| `tv_bridge.js` | Bridge TradingView (multi-TF EMA/RSI, metals via OANDA) |

## Setup

```bash
# 1. Dependensi: node >= 14 (untuk tv_bridge), python3
cd /tmp && git clone --depth 1 https://github.com/Mathieu2301/TradingView-API tvapi
cd tvapi && npm install

# 2. .env (lihat bagian Environment)

# 3. Dry run 1 iterasi:
python3 dewa_live.py --once

# 4. Dry run loop terus (scan tiap 60s):
python3 dewa_live.py

# 5. Laporan 24 jam:
python3 dewa_live.py --report
```

## Environment (`.env` / export)

```bash
LLM_BASE_URL=https://<gateway-openai-compatible>/v1
LLM_API_KEY=<key>
LLM_MODEL=auto
# Hanya untuk mode --live (eksekusi beneran):
BINANCE_API_KEY=
BINANCE_API_SECRET=
```

## Mode

- **DRY RUN (default)** — tanpa `BINANCE_API_KEY`: semua posisi virtual, log ke
  `dewa_live_log.jsonl`, state di `dewa_live_state.json`.
- **LIVE** — `python3 dewa_live.py --live` + API key Binance terisi (Futures permission,
  withdraw NONAKTIF). Order SL/TP conditional closePosition via `order_guard`.

## Backtest (bukti, jujur)

9 engine, ~60k trade simulasi, IS/OOS terpisah. Fade-ekstrem + rulebook ketat =
paling dekat breakeven (IS +$0.93 / OOS -$1.79 @ margin $2 lev 10x). V15 StochRSI
cross original pada rulebook sama: -$70.50. **Tidak ada klaim profit** — dry run 2
minggu adalah ujian sesungguhnya. LLM bisa ditolak oleh aturan mati; grade C tidak
pernah sampai ke bos.

## Disclaimer

Edukasi & riset. Bukan saran finansial. Trading futures berleverage tinggi dapat
menghapus modal. Gunakan dana dingin.
