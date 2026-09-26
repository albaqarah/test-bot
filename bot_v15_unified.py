#!/usr/bin/env python3
"""
bot_v15_unified.py — Bot V15 + arsitektur TradingAgents + data TradingView, 1 LLM agent.

Arsitektur (digabung dari 3 repo):
- [TradingAgents] Regime agent    : market regime deteksi (trend/range/chop) dari EMA multi-TF
- [TradingAgents] Bull/Bear debate: digabung jadi 1 agent — agent melihat pro & kontra sekaligus
- [TradingAgents] Risk debator    : conservative veto (funding ekstrem, ATR anomali)
- [TV-API]        Data            : candles + EMA/RSI multi-TF (5m/15m/1h) via TradingView bridge
- [V15+JEV]       Grade A/B/C     : climax imbalance + CVD + volume; C dibuang
- [V15]           Eksekusi        : BE-system + wick rejection + RR 3:1 bonus (konfig terbaik kita)

1 LLM agent menerima SATU briefing lengkap: regime, multi-TF TA, dominance proxy,
orderbook proxy (imbalance+CVD), funding, grade — output JSON CONFIRMED/REJECT.

Usage live : python3 bot_v15_unified.py live --pairs BTCUSDT,ETHUSDT --margin 2 --lev 10
Usage backtest: python3 bot_v15_unified.py backtest --pairs ALL --margin 2 --lev 10
LLM config : env LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (OpenAI-compatible)
"""
import os, sys, json, math, time, argparse, subprocess, urllib.request

BINANCE = "https://fapi.binance.com"
BE_OFFSET = 0.06          # % di atas entry untuk BE (biar > fee 2 sisi maker)
TP_RR = 3.0               # RR 3:1 — TP = 3x jarak BE (bonus)
MAX_LEV = 10
RISK_PCT = 1.0            # risk 1% equity per trade

# ---------- data layer (Binance utk OHLCV/funding/CVD proxy, TV utk multi-TF TA) ----------
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "v15unified/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def klines(symbol, interval="5m", limit=1000):
    return http_json(f"{BINANCE}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}")

def funding(symbol):
    try:
        d = http_json(f"{BINANCE}/fapi/v1/fundingRate?symbol={symbol}&limit=3")
        return float(d[-1]["fundingRate"])
    except Exception:
        return 0.0

TV_SYMBOL_MAP = {"XAUUSDT": "OANDA:XAUUSD", "XAGUSDT": "OANDA:XAGUSD",
                 "XPTUSDT": "OANDA:XPTUSD", "PAXGUSDT": "OANDA:XAUUSD"}

def tv_ta(symbol):
    """Multi-TF TA dari TradingView bridge. Fallback None jika TV down."""
    try:
        sym = TV_SYMBOL_MAP.get(symbol, f"BINANCE:{symbol}")
        out = subprocess.run(["node", os.path.join(os.path.dirname(os.path.abspath(__file__)),"tv_bridge.js"), sym],
                             capture_output=True, text=True, timeout=40)
        return json.loads(out.stdout)
    except Exception:
        return None

def cvd_proxy(k):
    """CVD proxy dari taker flow candle (JEV method): sum(close>=open ? vol : -vol)."""
    cvd, out = 0.0, []
    for c in k:
        o, h, l, cl, v = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
        cvd += v if cl >= o else -v
        out.append(cvd)
    return out

# ---------- grade engine (dari v15_grade.py, disederhanakan utk live) ----------
def grade_signal(k, i, cvd):
    o, h, l, c = (float(k[i][j]) for j in (1, 2, 3, 4))
    rng = h - l
    if rng <= 0: return None, {}
    imb = ((l - min(o, c)) - (max(o, c) - h)) / rng   # lower-wick dominance
    vol = float(k[i][5])
    vsma = sum(float(x[5]) for x in k[max(0, i-19):i]) / max(1, min(20, i))
    cvd_slope = cvd[i] - cvd[max(0, i-6)]
    sc = {"imb": round(imb, 3), "vol_x": round(vol / vsma, 2) if vsma else 0,
          "cvd_slope": round(cvd_slope, 2), "rng_atr": rng / max(1e-9, float(k[i-1][2]) - float(k[i-1][3]))}
    long_ok = imb <= -0.35 and vol > vsma and cvd_slope > 0
    short_ok = imb >= 0.35 and vol > vsma and cvd_slope < 0
    extreme = abs(imb) > 0.5 and sc["rng_atr"] > 1.5
    if long_ok and extreme: return "A", sc
    if short_ok and extreme: return "A", sc
    if long_ok or short_ok: return "B", sc
    return "C", sc

# ---------- regime agent (TradingAgents style, deterministik) ----------
def regime(tv):
    if not tv or not tv.get("tf60", {}).get("ta"):
        return {"regime": "UNKNOWN", "bias": "NEUTRAL", "source": "binance_fallback"}
    f = lambda tf, k: tv[tf]["ta"][k]
    e60_20, e60_50, r60 = f("tf60", "ema20"), f("tf60", "ema50"), f("tf60", "rsi")
    e15_20, e15_50 = f("tf15", "ema20"), f("tf15", "ema50")
    px = f("tf5", "last_close")
    trend_up = px > e60_20 > e60_50 and e15_20 > e15_50
    trend_dn = px < e60_20 < e60_50 and e15_20 < e15_50
    if trend_up:   return {"regime": "TREND_UP",   "bias": "LONG_ONLY",  "source": "tradingview"}
    if trend_dn:   return {"regime": "TREND_DOWN", "bias": "SHORT_ONLY", "source": "tradingview"}
    if 40 <= r60 <= 60: return {"regime": "CHOP",  "bias": "NO_TRADE",   "source": "tradingview"}
    return {"regime": "RANGE", "bias": "NEUTRAL", "source": "tradingview"}

# ---------- 1 LLM agent (TradingAgents graph dipadatkan jadi 1 prompt) ----------
SYSTEM_PROMPT = """Kamu adalah single trading agent (arsitektur TradingAgents dipadatkan):
bull/bear researcher + risk debator + trader dalam satu otak.
Terima briefing JSON: regime, multi-TF TA (TradingView), grade sinyal, imbalance, CVD,
funding, wick rejection. Tugasmu:
1. Bull case vs bear case dari data (2-3 baris mental, tanpa output).
2. Risk check konservatif: funding ekstrem melawan arah, regime CHOP/NO_TRADE, grade C.
3. Final decision.
ATURAN KERAS: grade C = REJECT. regime NO_TRADE = REJECT. funding melawan >0.1% = REJECT.
Output HANYA JSON: {"decision":"CONFIRMED|REJECT","confidence":0-100,"side":"LONG|SHORT","reason":"singkat"}"""

def llm_decide(briefing):
    base = os.environ.get("LLM_BASE_URL") or os.environ.get("CUSTOM_BASE_URL")
    key = os.environ.get("LLM_API_KEY") or os.environ.get("CUSTOM_API_KEY")
    model = os.environ.get("LLM_MODEL", os.environ.get("CUSTOM_MODEL", "auto"))
    if not base or not key:
        # fallback deterministik bila LLM belum diset — aturan yang sama dgn backtest gate
        ok = (briefing["grade"] in ("A", "B") and briefing["regime"]["bias"] != "NO_TRADE"
              and not (abs(briefing["funding"]) > 0.001 and
                       (briefing["funding"] > 0) == (briefing["side"] == "LONG")))
        return {"decision": "CONFIRMED" if ok else "REJECT",
                "confidence": 60 if ok else 0, "side": briefing["side"],
                "reason": "deterministic_gate_fallback", "llm": False}
    body = json.dumps({
        "model": model, "temperature": 0.1, "max_tokens": 2000,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": json.dumps(briefing)}],
    }).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            msg = json.loads(r.read())["choices"][0]["message"]
        txt = msg.get("content") or ""
        # gateway reasoning model bisa habiskan token di reasoning_content — cek sisa field
        if not txt.strip():
            txt = msg.get("reasoning_content") or ""
            rc = txt[txt.rfind("{"):txt.rfind("}") + 1]
            if rc: txt = rc
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
        d = json.loads(txt); d["llm"] = True
        return d
    except Exception as e:
        return {"decision": "REJECT", "confidence": 0, "reason": f"llm_error:{e}", "llm": False}

# ---------- eksekusi (BE-system, dari bewick.py — konfig terbaik) ----------
def plan_trade(side, entry, grade):
    be_px = entry * (1 + BE_OFFSET/100 if side == "LONG" else 1 - BE_OFFSET/100)
    risk = abs(entry - be_px)
    tp_px = entry + TP_RR * risk if side == "LONG" else entry - TP_RR * risk
    sl_px = entry - risk if side == "LONG" else entry + risk   # SL awal 1R, langsung geser ke BE
    return {"side": side, "entry": entry, "be": be_px, "tp": tp_px, "sl_initial": sl_px,
            "grade": grade, "lev": MAX_LEV, "margin_usd": 2.0}

# ---------- live loop ----------
def run_live(pairs):
    positions = {}
    print(f"[v15-unified] live loop start, pairs={pairs}", flush=True)
    while True:
        for sym in pairs:
            try:
                k = klines(sym, "5m", 200)
                i = len(k) - 2  # candle closed terakhir
                cvd = cvd_proxy(k)
                g, sc = grade_signal(k, i, cvd)
                if g == "C" or sym in positions: continue
                o, c = float(k[i][1]), float(k[i][4])
                side = "LONG" if c >= o else "SHORT"
                tv = tv_ta(sym)
                reg = regime(tv)
                fund = funding(sym)
                brief = {"symbol": sym, "grade": g, "score": sc, "side": side,
                         "regime": reg, "funding": fund,
                         "tv": {tf: tv[tf]["ta"] if tv and tv.get(tf) else None
                                for tf in ("tf5", "tf15", "tf60")},
                         "wick_rejection": sc.get("imb", 0) <= -0.35 if side == "LONG" else sc.get("imb", 0) >= 0.35}
                d = llm_decide(brief)
                print(f"[{sym}] grade={g} side={side} regime={reg['regime']} "
                      f"funding={fund:.4%} llm={d.get('llm')} -> {d['decision']} "
                      f"conf={d.get('confidence')} ({d.get('reason','')[:60]})", flush=True)
                if d["decision"] == "CONFIRMED":
                    entry = float(k[-1][1])  # open candle berikutnya — anti-lookahead
                    p = plan_trade(side, entry, g)
                    positions[sym] = p
                    print(f"   >> PLAN {json.dumps(p)}", flush=True)
            except Exception as e:
                print(f"[{sym}] err: {e}", flush=True)
        time.sleep(30)

# ---------- backtest (full pairs, margin $2 lev 10x, BE+wick system) ----------
def run_backtest(pairs, margin=2.0, lev=10):
    import backtest_engine as be  # reuse engine V15 yang sudah ada
    return be.run(pairs, margin=margin, lev=lev, mode="unified")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["live", "backtest"])
    ap.add_argument("--pairs", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--margin", type=float, default=2.0)
    ap.add_argument("--lev", type=int, default=10)
    a = ap.parse_args()
    pairs = [p.strip() for p in a.pairs.split(",")]
    if a.mode == "live":
        run_live(pairs)
    else:
        print(json.dumps(run_backtest(pairs, a.margin, a.lev), indent=2))
