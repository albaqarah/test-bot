#!/usr/bin/env python3
"""
tg_notify.py — Notifikasi Telegram utk bot dewa.
Env: TG_BOT_TOKEN, TG_CHAT_ID  (dikirim tiap: open, exit win/lose, saldo net harian, briefing)
"""
import os, json, urllib.request, urllib.parse

def send(text, chat_id=None, token=None):
    tok = token or os.environ.get("TG_BOT_TOKEN", "")
    cid = chat_id or os.environ.get("TG_CHAT_ID", "")
    if not tok or not cid:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": cid, "text": text,
                                       "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False

def fmt_open(e):
    return (f"🎯 <b>ENTRY {e['side']}</b> {e['symbol']}  [{e.get('grade','?')}]"
            f"\nEntry: <code>{e['entry']}</code>"
            f"\nSL: <code>{round(e['sl'],6)}</code> | TP: <code>{round(e['tp'],6)}</code>"
            f"\n🧠 <b>Bos LLM</b> conf={e.get('conf')}"
            f"\n💬 \"{e.get('reason','')}\"")

def fmt_exit(e, saldo):
    win = e.get('pnl', 0) > 0
    emoji = "✅ WIN" if win else ("➖ BE" if e.get('hit') in ('BE','TIME') else "❌ LOSE")
    return (f"{emoji} <b>CLOSE {e.get('hit')}</b> {e['symbol']} ({e.get('side')})"
            f"\nPnL: <b>${e.get('pnl',0):+.2f}</b>  |  Saldo net (virtual): <b>${saldo:+.2f}</b>"
            f"\n🧠 Bos conf saat entry: {e.get('conf')}"
            f"\n💬 \"{e.get('reason','')}\"")

def fmt_briefing(rep, open_positions, decisions_sample):
    lines = [f"🌅 <b>MORNING BRIEFING — Bot DEWA</b>",
             f"━━━━━━━━━━━━━━━━━━━",
             f"Sinyal 24 jam: <b>{rep.get('decisions',0)}</b> | Bos acc: <b>{rep.get('accepted',0)}</b>",
             f"Exit 24 jam: {rep.get('exits',0)} {rep.get('hits',{})}",
             f"PnL 24 jam: <b>${rep.get('pnl_24h',0):+.2f}</b> (virtual)",
             f"Posisi terbuka: <b>{len(open_positions)}</b>"]
    for sym, p in list(open_positions.items())[:5]:
        lines.append(f"  • {sym} {p['side']} conf={p.get('conf')}")
    if decisions_sample:
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("🧠 <b>Reasoning bos terakhir:</b>")
        for d in decisions_sample[:3]:
            lines.append(f"  • {d.get('symbol')} {d.get('side')} → {d.get('decision')} ({d.get('conf')}): \"{d.get('reason','')}\"")
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ DRY RUN — virtual, bukan duit beneran")
    return "\n".join(lines)
