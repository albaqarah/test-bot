#!/usr/bin/env python3
"""
tg_notify.py v2 - Notifikasi Telegram bot DEWA (gaya keren, ada jam WIB).
"""
import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

def _load_env(path='/home/agentuser/.env'):
    try:
        for line in open(path):
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception: pass
_load_env()

def now_wib():
    return datetime.now(WIB).strftime('%d %b %Y - %H:%M:%S WIB')

def send(text, chat_id=None, token=None):
    tok = token or os.environ.get("TG_BOT_TOKEN", "")
    cid = chat_id or os.environ.get("TG_CHAT_ID", "")
    if not tok or not cid:
        return False
    for attempt in range(3):
        try:
            data = urllib.parse.urlencode({"chat_id": cid, "text": text,
                                           "parse_mode": "HTML"}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("ok", False)
        except Exception as e:
            import sys, time as _t
            print(f"[tg] send fail #{attempt+1}: {e!r}", file=sys.stderr, flush=True)
            _t.sleep(2*(attempt+1))
    return False

def price_of(sym):
    try:
        d=json.loads(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}",timeout=8).read())
        return float(d['price'])
    except Exception:
        return None

SIDE = {"L":"LONG","S":"SHORT","LONG":"LONG","SHORT":"SHORT"}

def fmt_open(e):
    px = price_of(e['symbol'])
    lv = NL + "💰 Harga live: <code>%s</code>" % px if px else ""
    return ("⚔️ <b>SNIPER FIRING</b> ⚔️"
        + NL + "━━━━━━━━━━━━━━━━━━"
        + NL + f"🎯 <b>{SIDE.get(e['side'],e['side'])} {e['symbol']}</b> ┃ GRADE <b>{e.get('grade','?')}</b>"
        + NL + f"💵 Entry: <code>{e['entry']}</code>" + lv
        + NL + "💸 Margin $2 × 10x (notional $20)"
        + NL + f"🩸 Stop Loss : <code>{round(e['sl'],6)}</code>"
        + NL + f"💥 Take Profit: <code>{round(e['tp'],6)}</code> (RR 1:{e.get('tp_rr',3):g}{', MODE CHOP SNIPER' if e.get('tp_rr')==2.0 else ''})"
        + NL + f"⏰ {now_wib()}"
        + NL + "━━━━━━━━━━━━━━━━━━"
        + NL + f"🧠 <b>BOS LLM</b> conf: <b>{e.get('conf')}/100</b>"
        + NL + f"🗣 \"<i>{e.get('reason','')}</i>\"")

def fmt_exit(e, saldo):
    win = e.get('pnl', 0) > 0
    if win: head, art = "🏆 <b>WIN</b>", "💎"
    elif e.get('hit') in ('BE','TIME'): head, art = "⚖️ <b>BREAKEVEN</b>", "🌀"
    else: head, art = "☠️ <b>LOSE</b>", "🩸"
    px = e.get('exit_px') or price_of(e['symbol'])   # harga eksekusi asli (singkron app), fallback live
    lv = NL + f"💰 Exit harga: <code>{px}</code>" if px else ""
    return (art + " " + head + f" - {e.get('hit')}"
        + NL + "━━━━━━━━━━━━━━━━━━"
        + NL + f"🎯 {SIDE.get(e.get('side'),e.get('side'))} {e['symbol']}" + lv
        + NL + "💸 Margin $2 × 10x"
        + NL + f"📊 PnL: <b>${e.get('pnl',0):+.2f}</b>"
        + NL + f"🏦 Saldo net (virtual): <b>${saldo:+.2f}</b>"
        + NL + f"⏰ {now_wib()}"
        + NL + "━━━━━━━━━━━━━━━━━━"
        + NL + f"🧠 Bos conf saat entry: {e.get('conf')}/100"
        + NL + f"🗣 \"<i>{e.get('reason','')}</i>\"")

def fmt_briefing(rep, open_positions, decisions_sample):
    acc = rep.get('accepted',0); dec = rep.get('decisions',0)
    rate = f"{100*acc/dec:.0f}%" if dec else "-"
    lines = ["🌅 <b>MORNING BRIEFING - DEWA SNIPER</b> 🌅",
             f"📅 {now_wib()}",
             "━━━━━━━━━━━━━━━━━━",
             f"📡 Sinyal 24 jam: <b>{dec}</b> → Bos acc: <b>{acc}</b> ({rate})",
             f"⚔️ Exit 24 jam: <b>{rep.get('exits',0)}</b>  {rep.get('hits',{})}",
             f"💵 PnL 24 jam: <b>${rep.get('pnl_24h',0):+.2f}</b> <i>(virtual)</i>",
             f"🔓 Posisi terbuka: <b>{len(open_positions)}</b>"]
    for sym, p in list(open_positions.items())[:5]:
        lines.append(f"   • {p['side']} {sym} ┃ conf {p.get('conf')}")
    if decisions_sample:
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("🧠 <b>REASONING BOS TERAKHIR</b>")
        for d in decisions_sample[:3]:
            lines.append(f"  ▪️ {d.get('symbol')} {d.get('side')} → <b>{d.get('decision')}</b> ({d.get('conf')})")
            lines.append(f"     🗣 \"<i>{d.get('reason','')}</i>\"")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ DRY RUN - virtual, bukan duit beneran")
    return NL.join(lines)

NL = chr(10)
