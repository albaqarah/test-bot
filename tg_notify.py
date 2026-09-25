#!/usr/bin/env python3
"""
tg_notify.py v3 — gaya notif v15 (user-request 24 Sep), isi sistem DEWA v6.2.
Format: MORNING BRIEFING / BOT START / STOP / RESTART / ENTRY / TRAIL LOCK / CLOSED.
Semua angka rekap dihitung dari log asli 24 jam.
"""
import os, json, urllib.request, urllib.parse, math
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
NL = chr(10)
DIV = "━━━━━━━━━━━━━━━━━━━━━━━━━━"


def _wib_now():
    """Waktu notif dibentuk — WIB (UTC+7), format gaya v15."""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=7))).strftime('%d %b %Y - %H:%M:%S WIB')


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
ARROW = {"LONG":"🟢 LONG","SHORT":"🔴 SHORT"}
SIDE_ART={"LONG":"🟢","SHORT":"🔴"}

def _fmt_usd(v, signed=True):
    return f"{v:+.2f} USDT" if signed else f"{v:.2f} USDT"

def _bar(pct, w=10):
    n=max(0,min(w,round(pct/100*w)))
    return "▰"*n+"▱"*(w-n)

def _wr(resume):
    t=resume.get('w',0)+resume.get('l',0)
    return 100*resume.get('w',0)/t if t else 0.0

def _pf(resume):
    gl=resume.get('gross_loss',0)
    return resume.get('gross_win',0)/gl if gl>0 else (float('inf') if resume.get('gross_win') else 0.0)

_BRIEF_MARK='/home/agentuser/.dewa_briefing_mark'
def _briefing_cutoff():
    """Cutoff rekap: sejak morning briefing terakhir (reset 0/0 tiap briefing)."""
    import os as _os
    try: return _os.path.getmtime(_BRIEF_MARK)
    except Exception: return None

def _resume24():
    """Rekap periode sejak morning briefing terakhir (fallback 24 jam rolling) — dipakai semua notif."""
    import time as _time
    out={'w':0,'l':0,'gross_win':0.0,'gross_loss':0.0,'fee':0.0,'net':0.0,'best':None,'worst':None}
    per={}
    try:
        _bm=_briefing_cutoff()
        cutoff=_bm if _bm else (_time.time()-86400)
        for line in open('/home/agentuser/dewa_live_log.jsonl'):
            try: d=json.loads(line)
            except Exception: continue
            if d.get('event')!='exit': continue
            ts=d.get('ts','')
            try:
                from datetime import datetime as _dt
                t=_dt.fromisoformat(ts.replace('+00:00','+00:00')).timestamp()
            except Exception: continue
            if t < cutoff: continue
            pnl=d.get('pnl',0)
            out['fee']+=0.02  # fee roundtrip sim per trade (2×0.05% × notional $20)
            if pnl>0.02: out['w']+=1; out['gross_win']+=pnl+0.02
            elif pnl>=-0.02: pass  # LOCK/BE rata — bukan win bukan lose (gak merusak WR)
            else: out['l']+=1; out['gross_loss']+=abs(pnl)+0.02
            out['net']+=pnl
            per[d['symbol']]=per.get(d['symbol'],0)+pnl
    except Exception: pass
    if per:
        bs=sorted(per.items(), key=lambda x:-x[1])
        out['best']=(bs[0][0], bs[0][1]); out['worst']=(bs[-1][0], bs[-1][1])
    return out

def _tradfi_line():
    try:
        import tradfi_session as tfs
        st,why,et=tfs.tradfi_label()
        icon='🟢' if st=='OPEN' else '🌙'
        whytxt=f" ({why})" if why else ""
        return f"🏛️ TradFi    {icon} {st}{whytxt} ({et})"
    except Exception:
        return "🏛️ TradFi    ❓"

def _mode_line():
    live=os.environ.get('MODE','dry').strip().lower()=='live'
    return ('🔴 LIVE' if live else '⚪ DRY RUN (virtual)')

def _bos_line():
    prov=os.environ.get('BOS_PROVIDER','jev').strip().lower()
    return "🤖 🟢 JEV" if prov=='jev' else "🤖 🟢 lightvela"

def _equity(saldo):
    live=os.environ.get('MODE','dry').strip().lower()=='live'
    return f"💰 Ekuitas   ${saldo:+.2f} ({'LIVE' if live else 'DRY'})"

def _slots(st_open, maxpos=5):
    return f"🎟️ Slot      {len(st_open)}/{maxpos}"

def _regime_line():
    try:
        import reversion_bot as rb
        reg=rb.regime_1h('BTCUSDT')
        return f"🧭 Regime    {str(reg).upper()} (BTC 1h)"
    except Exception:
        return "🧭 Regime    MIXED"

# ---------- START / STOP / RESTART ----------
def fmt_start(saldo, n_open=0, maxpos=5, n_pair=41):
    r=_resume24()
    return (f"🟢 <b>BOT START · DEWA SNIPER v6.2</b>" + NL + DIV
        + NL + f"🧾 Mode      {_mode_line()}"
        + NL + _equity(saldo)
        + NL + "💵 Margin    $2.00/trade · notional $20.00"
        + NL + f"🎟️ Slot      {maxpos} · 1 posisi/pair · cd 30m"
        + NL + "🪙 Pair      41 (38 crypto + 3 logam + PAXG)"
        + NL + "🎯 TP/SL     SL 1.2% · TP 4R trend / 3R chop (bos bisa override)"
        + NL + "🛡️ BE        TRAIL aktif: kunci +0.6% → puncak −0.3%"
        + NL + _tradfi_line()
        + NL + _bos_line()
        + NL + "🖥️ UI        log ringkas")

def fmt_stop(saldo, n_open=0, reason='manual', open_syms=''):
    r=_resume24()
    pos=f"{n_open} terbuka ({open_syms})" if n_open else "tidak ada"
    return (f"🛑 <b>BOT STOP · DEWA SNIPER v6.2</b>" + NL + DIV
        + NL + f"🏷️ Alasan    {reason}"
        + NL + f"📊 24 jam    {r['w']}W/{r['l']}L · WR {_wr(r):.1f}% · Net {_fmt_usd(r['net'])}"
        + NL + f"💰 Ekuitas   ${saldo:+.2f}"
        + NL + f"📌 Posisi    {pos}"
        + NL + DIV
        + NL + "Posisi yang masih terbuka TIDAK ikut tertutup. Pantau manual di app.")

def fmt_restart(saldo, n_open=0, maxpos=5):
    return fmt_start(saldo, n_open, maxpos)

# ---------- ENTRY (gaya v15) ----------
def fmt_open(e):
    """e: symbol,side,entry,sl,tp,tp_rr,conf,reason,regime,mclass,rsi6,saldo,n_open,variant"""
    side=SIDE.get(e['side'],e['side'])
    notional=e.get('notional',20.0)
    variant=e.get('variant','')
    var_txt=f" (bos {variant} anti-wick)" if variant=='WIDE' else (f" (bos {variant})" if variant else "")
    _long = e['side'] in ('LONG','L')
    sl_pct=abs(e['sl']/e['entry']-1)*100*(-1 if _long else 1)   # LONG SL di bawah = minus; SHORT = plus
    tp_pct=abs(e['tp']/e['entry']-1)*100*(1 if _long else -1)   # TP sebaliknya
    conf=e.get('conf')
    mom=""
    if e.get('mclass') or e.get('rsi6') is not None:
        mom=NL+f"🧭 Momentum {e.get('mclass','?')} · RSI6 {e.get('rsi6','?')}"
    r=_resume24()
    return ("🚀 <b>ENTRY</b> · "+e['symbol']+" · "+SIDE_ART.get(side,'')+f" <b>{side}</b>"
        + NL + DIV
        + NL + f"🧾 Mode   {_mode_line()}"
        + NL + f"💵 Entry  <code>{e['entry']}</code>"
        + NL + f"📦 Qty <code>{e.get('qty') if e.get('qty') else round(notional/e['entry'], 6)}</code> · Notional ${notional:.2f} · margin $2.00 ×10"
        + NL + f"🎯 TP     <code>{e['tp']}</code>  {tp_pct:+.2f}% (RR 1:{e.get('tp_rr',3):g})"
        + NL + f"🛡️ SL     <code>{e['sl']}</code>  {sl_pct:+.2f}%{var_txt}"
        + NL + DIV
        + NL + f"🧭 Regime {e.get('regime','?')}"
        + NL + f"🧠 Bos conf: {conf}/100"
        + NL + _bos_line().replace('🤖 ','🤖 ')
        + NL + f"🧠  <i>{e.get('reason','')}</i>"
        + mom
        + NL + DIV
        + NL + f"🎟️ Slot {e.get('n_open','?')}/5 · {_equity(e.get('saldo',0)).replace('💰 Ekuitas   ','💰 Ekuitas ')}"
        + NL + f"📊 Hari ini {r['w']}W/{r['l']}L · WR {_wr(r):.1f}% · Net {r['net']:+.2f}"
        + NL + "⏰ "+_wib_now())

# ---------- TRAIL LOCK ----------
def fmt_trail_lock(sym, side, new_sl, entry, peak):
    mv=(new_sl-entry)/entry*(100 if side=='LONG' else -100)
    return (f"🛡️ <b>BREAKEVEN TRAIL LOCKED</b> · {sym} · {side}"
        + NL + f"SL digeser ke <code>{round(new_sl,6)}</code> (kunci profit {mv:+.2f}% dari puncak {round(peak,6)})"
        + NL + "⏰ "+_wib_now())

# ---------- CLOSED (gaya v15) ----------
def fmt_exit(e, saldo, n_open=None):
    pnl=e.get('pnl',0)
    hit=e.get('hit','')
    if pnl>0.005: head,art="✅ CLOSED — WIN","💎"
    elif pnl>=-0.02: head,art="⚖️ CLOSED — RATA","🌀"
    else: head,art="❌ CLOSED — LOSE","🩸"
    exit_px=e.get('exit_px') or price_of(e['symbol'])
    entry=e.get('entry')
    mv=0
    if entry and exit_px:
        mv=(exit_px-entry)/entry*100*(1 if e.get('side')=='LONG' else -1)
    roi=mv*10  # 10x
    dur=e.get('durasi') or (f"{e.get('bars',0)*5:.0f} menit" if e.get('bars') else "?")
    gross=pnl+0.02; fee=0.02
    r=_resume24()
    alasan={'TP':'take profit','WIN-LOCK':'trailing lock','LOCK':'trailing lock (nyaris fee)',
            'BE':'breakeven guard','SL':'stop loss','TIME':'max hold'}[hit] if hit in ('TP','WIN-LOCK','LOCK','BE','SL','TIME') else hit.lower()
    sym=e['symbol']
    lines=[art+" "+head+" · "+sym+" · "+str(e.get('side','')),
        DIV,
        f"▰{('▰'*max(0,min(9,round(abs(roi)/2))))}{'▱'*max(0,9-max(0,min(9,round(abs(roi)/2))))}  {roi:+.2f}% ROI (10x)",
        DIV,
        f"💵 Entry → Exit   {entry} → {exit_px}",
        f"🏷️ Alasan       {alasan}",
        f"⏱️ Durasi       {dur}",
        DIV,
        f"📐 Gross        {_fmt_usd(gross)} ({mv:+.3f}%)",
        f"🧾 Fee          -{fee:.3f} USDT",
        f"💰 NET        {_fmt_usd(pnl)}",
        DIV,
        "📉 REKAP HARI INI",
        f"├ W/L      {r['w']}W / {r['l']}L",
        f"├ Win rate {_wr(r):.1f}%",
        f"└ Net      {_fmt_usd(r['net'])}",
        DIV,
        f"💰 Ekuitas ${saldo:+.2f} ({'LIVE' if os.environ.get('MODE','dry')=='live' else 'DRY'})"
        + (f"  ·  🎟️ Slot {n_open}/5" if n_open is not None else "")
        + NL + "🔒 Cooldown "+sym+" 30m"
        + NL + "⏰ "+_wib_now()]
    return NL.join(lines)

# ---------- MORNING BRIEFING (gaya v15) ----------
def fmt_briefing(rep, open_positions, decisions_sample=None, saldo=0.0, uptime=''):
    r=_resume24()
    trade=r['w']+r['l']
    pf=_pf(r); pf_txt=f"{pf:.2f}" if pf!=float('inf') else "∞"
    lines=["☀️ <b>MORNING BRIEFING · "+datetime.now(WIB).strftime('%d %b %Y')+"</b>",
        DIV,
        "⏰ "+datetime.now(WIB).strftime('%H:%M')+" WIB · periode 24 jam terakhir",
        DIV,
        "📊 PERFORMA",
        f"├ Trade     {trade}",
        f"├ W / L     {r['w']}W / {r['l']}L",
        f"├ Win rate  {_bar(_wr(r))} {_wr(r):.1f}%",
        f"└ PF        {pf_txt}",
        DIV,
        "💰 KEUANGAN",
        f"├ Gross     {_fmt_usd(r['gross_win'])}",
        f"├ Fee       -{r['fee']:.2f} USDT",
        f"├ NET       {_fmt_usd(r['net'])} (24 jam)",
        f"└ Ekuitas   ${saldo:+.2f} ({'LIVE' if os.environ.get('MODE','dry')=='live' else 'DRY'})",
        DIV,
        "🔥 LEADERBOARD"]
    if r['best']: lines.append(f"├ 🔼 Terbaik   {r['best'][0].replace('USDT','/USDT')} ({r['best'][1]:+.2f} USDT)")
    if r['worst']: lines.append(f"└ 🔽 Terburuk {r['worst'][0].replace('USDT','/USDT')} ({r['worst'][1]:+.2f} USDT)")
    lines+= [DIV,
        _regime_line(),
        _tradfi_line(),
        "🪙 Pair      41 (38 crypto + 3 logam + PAXG)",
        f"🎟️ Slot      {len(open_positions)}/5",
        _bos_line(),
        f"🧾 Mode      {_mode_line()}" + (f" · uptime {uptime}" if uptime else "")]
    if decisions_sample:
        lines.append(DIV)
        lines.append("🧠 REASONING BOS TERAKHIR")
        for d in decisions_sample[:3]:
            lines.append(f"  ▪️ {d.get('symbol')} {d.get('side')} → {d.get('decision')} ({d.get('conf')})")
    return NL.join(lines)
