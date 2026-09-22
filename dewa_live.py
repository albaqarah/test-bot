#!/usr/bin/env python3
"""
dewa_live.py — BOT LIVE FINAL (dry-run mode default: eksekusi virtual).
Pipeline lengkap: Data -> Kurir matematika -> Grade A/B -> LLM bos (skill dewa)
-> Risk gate (max 5 posisi global) -> Eksekusi virtual -> Janitor SL/TP.

Struktur = persis breakdown yang sudah di-review user:
1. Data      : Binance klines 5m/1h + funding; TV multi-TF via tv_bridge.js (best effort)
2. Kurir     : reversion_bot.gen_signals (RSI+z-score+wick+volume, Wilder RSI)
3. Grade     : A (climax+wick ekstrem) / B (inti) — C tidak pernah disetor
4. Bos       : dewa_skill.SYSTEM_PROMPT, 1 LLM agent, output JSON
5. Risk      : order_guard.MAX_GLOBAL_POSITIONS=5, 1 posisi/pair
6. Eksekusi  : entry open candle berikutnya, margin $2, lev 10x,
               SL max(0.35%,0.4%), TP 3R, BE-shift +0.1% -> +0.06%, max hold 480 bar
7. Janitor   : verifikasi SL/TP tiap 5s (di dry run: logika yang sama, virtual)
8. Log       : dewa_live_log.jsonl (tiap keputusan) + dewa_live_state.json (posisi terbuka)
               Cron harian baca log ini untuk laporan.

Usage: python3 dewa_live.py --pairs ALL --once   (1 iterasi, untuk cron)
       python3 dewa_live.py --pairs ALL          (loop terus)
       python3 dewa_live.py --live               (EKSEKUSI BENERAN — butuh API key, default OFF)
"""
import importlib.util, json, os, sys, time, argparse, subprocess
from datetime import datetime, timezone

def _load_env(path='/home/agentuser/.env'):
    try:
        for line in open(path):
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception: pass
_load_env()

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)
import reversion_bot as rb
import dewa_skill as ds
import order_guard as og
import tg_notify as tg
import order_cleanup as oc
import hybrid_rules as hr

og.MAX_GLOBAL_POSITIONS=5

# ==== TUNING — bisa dioverride dari .env ====
def _cfg(k, default, cast=float):
    raw=os.environ.get(k)
    if raw is None: return default
    try: return cast(str(raw).split('#',1)[0].strip())
    except Exception: return default
FEE=0.0005
LEV=_cfg('LEVERAGE',10,int)
MARGIN=_cfg('MARGIN_USD',2.0)/100.0     # env = margin USD beneran ($2 = $2); internal x100
SL_PCT=_cfg('SL_PCT',0.004)             # SL = % dari harga entry
TP_RR_TREND=_cfg('TP_RR_TREND',3.0)     # RR saat regime TREND_UP/DOWN
TP_RR_CHOP=_cfg('TP_RR_CHOP',2.0)       # RR saat regime RANGE (chop sniper)
BE_TRIG=_cfg('BE_TRIG',0.0010)          # shift BE kalau profit >= ini
BE_OFF=_cfg('BE_OFF',0.0006)            # BE = entry +/- ini (harus > fee roundtrip 0.1%? -> 0.06%)
MAXHOLD=_cfg('MAXHOLD_TREND',480,int)   # max hold bar 5m utk trend (480=40 jam)
MAXHOLD_CHOP=_cfg('MAXHOLD_CHOP',96,int)# max hold utk chop (96=8 jam)
COOLDOWN_MIN=_cfg('COOLDOWN_MIN',30,int)# re-entry cooldown per pair (menit)
SCAN_SEC=_cfg('SCAN_SEC',60,int)        # jeda antar scan (detik) saat idle
COOLDOWN_MS=COOLDOWN_MIN*60*1000
LIVE=os.environ.get('MODE','dry').strip().lower()=='live'   # MODE=live di .env -> eksekusi nyata

LOG='/home/agentuser/dewa_live_log.jsonl'
STATE='/home/agentuser/dewa_live_state.json'
LOCKF='/home/agentuser/dewa_live.lock'
# COOLDOWN_MS sekarang dari COOLDOWN_MIN (.env)

def acquire_lock(block_wait=0.0):
    """File-lock: cuma SATU proses boleh mutasi state (anti race condition).
    Return file-handle yg dipegang, atau None kalau proses lain pegang lock.
    LOCK HANGUS OTOMATIS kalau pegangnya mati (kernel melepas flock saat proses mati)."""
    import fcntl
    fh=open(LOCKF,'w')
    flag=fcntl.LOCK_EX | (fcntl.LOCK_NB if block_wait<=0 else 0)
    if block_wait<=0:
        try: fcntl.flock(fh,flag)
        except Exception: fh.close(); return None
    else:
        deadline=time.time()+block_wait
        while True:
            try: fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB); break
            except Exception:
                if time.time()>deadline: fh.close(); return None
                time.sleep(0.2)
    return fh

PAIRS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
       'LINKUSDT','DOTUSDT','LTCUSDT','BCHUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
       'WLDUSDT','ORDIUSDT','ENAUSDT','WIFUSDT','ONDOUSDT','HYPEUSDT','JUPUSDT','RUNEUSDT',
       'AAVEUSDT','UNIUSDT','FETUSDT','GALAUSDT','CRVUSDT','LDOUSDT','ARBUSDT','OPUSDT',
       'ATOMUSDT','FILUSDT','INJUSDT','SEIUSDT','TRXUSDT','PAXGUSDT','XAUUSDT','XAGUSDT','XPTUSDT']

def log(evt):
    evt['ts']=datetime.now(timezone.utc).isoformat()
    with open(LOG,'a') as f: f.write(json.dumps(evt)+'\n')

def load_state():
    try: return json.load(open(STATE))
    except Exception: return {'open':{}}

def save_state(st): json.dump(st, open(STATE,'w'), indent=1)

def fund_last(sym):
    try:
        import urllib.request
        d=json.loads(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1",timeout=8).read())
        return float(d[0]['fundingRate'])
    except Exception: return 0.0

def tv_ta(sym):
    """TV multi-TF best-effort; None kalau down."""
    try:
        from bot_v15_unified import TV_SYMBOL_MAP
        sym2=TV_SYMBOL_MAP.get(sym, f"BINANCE:{sym}")
        out=subprocess.run(["node","/home/agentuser/tv_bridge.js",sym2],
                           capture_output=True,text=True,timeout=40)
        d=json.loads(out.stdout)
        return {tf:(d[tf]['ta'] if d.get(tf) else None) for tf in ('tf5','tf15','tf60')}
    except Exception:
        return None

def llm_call(brief):
    base=os.environ.get("LLM_BASE_URL")
    key=os.environ.get("LLM_API_KEY") or os.environ.get("CUSTOM_API_KEY")
    model=os.environ.get("LLM_MODEL","auto")
    if not base:
        try:
            line=[l for l in open(os.path.expanduser('~/.hermes/config.yaml')) if 'base_url' in l][0]
            base=line.split('base_url:')[1].strip().split()[0]
        except Exception: return {"decision":"REJECT","confidence":0,"reason":"no_llm_config"}
    if not key: return {"decision":"REJECT","confidence":0,"reason":"no_api_key"}
    import urllib.request
    # ANTI-REASONING-BURN: gateway 'auto' = model reasoning; briefing penuh bikin dia
    # habis-kan semua token buat thinking -> JSON final gak pernah ditulis (finish=length).
    # Instruksi keras: langsung JSON (terbukti: reasoning 4885->3454 tok, finish=stop, 27s)
    FORCE_JSON=("\n\nOutput WAJIB: SATU baris JSON murni, mulai langsung dengan { tanpa teks pembuka:\n"
                '{"decision":"CONFIRMED"|"REJECT","confidence":0-100,"reason":"maksimal 20 kata","key_factor":"maksimal 12 kata"}\n'
                "JANGAN jelaskan proses berpikir. JANGAN tulis analisis. LANGSUNG JSON-nya saja.")
    body=json.dumps({"model":model,"temperature":0.1,"max_tokens":1500,
        "messages":[{"role":"system","content":ds.SYSTEM_PROMPT+FORCE_JSON},
                    {"role":"user","content":json.dumps(brief)}]}).encode()
    req=urllib.request.Request(base.rstrip('/')+"/chat/completions",data=body,
        headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    last_err='unknown'
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=60) as r:
                msg=json.loads(r.read())["choices"][0]["message"]
            txt=(msg.get("content") or "").strip()
            if not txt:
                txt=(msg.get("reasoning_content") or "").strip()
            i,j=txt.find("{"),txt.rfind("}")
            if i<0 or j<=i:
                raise ValueError("no_json_in_response")
            return json.loads(txt[i:j+1])
        except Exception as ex:
            last_err=str(ex)[:50]
            time.sleep(3)  # retry cepat, jangan gondok timer iterasi
    return {"decision":"REJECT","confidence":0,"reason":f"llm_err:{last_err}"}

def manage_open(st, k_cache):
    """Update posisi virtual: BE-shift, SL/TP hit, max-hold. Return realized pnl list."""
    realized=[]
    now=int(time.time()*1000)
    for sym in list(st['open'].keys()):
        p=st['open'][sym]
        try:
            k5=k_cache.get(sym) or vg.fetch_hist_klines(sym,'5m',3)
            k_cache[sym]=k5
            last=k5[-1]
            h,l=float(last[2]),float(last[3])
            side=p['side']
            # BE shift
            if not p['be_moved']:
                if side=='LONG' and h>=p['entry']*(1+BE_TRIG): p['be_moved']=True; p['sl']=p['entry']*(1+BE_OFF)
                if side=='SHORT' and l<=p['entry']*(1-BE_TRIG): p['be_moved']=True; p['sl']=p['entry']*(1-BE_OFF)
            hit=None; exit_px=None
            if side=='LONG':
                if l<=p['sl']: hit='BE' if p['be_moved'] else 'SL'; exit_px=p['sl']
                elif h>=p['tp']: hit='TP'; exit_px=p['tp']
            else:
                if h>=p['sl']: hit='BE' if p['be_moved'] else 'SL'; exit_px=p['sl']
                elif l<=p['tp']: hit='TP'; exit_px=p['tp']
            bars_open=(now-p['open_ts'])/300000
            maxhold=MAXHOLD_CHOP if p.get('regime')=='RANGE' else MAXHOLD
            if hit is None and bars_open>=maxhold: hit='TIME'; exit_px=float(last[4])
            if hit and LIVE:
                # posisi nyata: SL/TP di exchange yang nutup — bot tinggal notif PnL nyata dari kalkulasi
                mv=(exit_px-p['entry'])/p['entry']*(1 if side=='LONG' else -1)
                fee=2*FEE
                pnl=100*MARGIN*(mv*LEV-fee*LEV)  # estimasi (uang nyata dihitung Binance)
                realized.append({'sym':sym,'hit':hit,'pnl':round(pnl,2),'bars':round(bars_open,1),
                                 'conf':p.get('conf'),'grade':p.get('grade'),'side':side})
                log({'event':'exit','symbol':sym,'hit':hit,'pnl':pnl,'conf':p.get('conf'),'live':True})
                st['saldo']=round(st.get('saldo',0)+pnl,2)
                st.setdefault('cooldown',{})[sym]=now+COOLDOWN_MS
                reason=last_reason(sym, st)
                tg.send(tg.fmt_exit({'symbol':sym,'side':side,'hit':hit,
                                     'pnl':pnl,'conf':p.get('conf'),'reason':reason},
                                    st['saldo'])+'\n🟢 MODE LIVE')
                og.targets.pop(sym, None)   # posisi tutup -> janitor lepas
                del st['open'][sym]
                continue
            if hit:
                mv=(exit_px-p['entry'])/p['entry']*(1 if side=='LONG' else -1)
                fee=2*FEE if hit!='SL' else FEE+FEE  # SL full taker, lainnya maker-ish sim
                pnl=100*MARGIN*(mv*LEV-fee*LEV)
                realized.append({'sym':sym,'hit':hit,'pnl':round(pnl,2),'bars':round(bars_open,1),
                                 'conf':p.get('conf'),'grade':p.get('grade'),'side':side})
                log({'event':'exit','symbol':sym,'hit':hit,'pnl':pnl,'conf':p.get('conf')})
                st['saldo']=round(st.get('saldo',0)+pnl,2)
                # cooldown: jangan re-entry pair yg baru exit dalam 30 menit (anti duplikasi)
                st.setdefault('cooldown',{})[sym]=now+COOLDOWN_MS
                # poin 4: pastikan ga ada SL/TP nyantol setelah close
                oc.cleanup_leftovers(sym, live=og.API_KEY and og.API_SECRET and LIVE)
                # poin 2: notifikasi Telegram (win/lose + saldo net + reasoning)
                reason=last_reason(sym, st)
                tg.send(tg.fmt_exit({'symbol':sym,'side':p.get('side'),'hit':hit,
                                     'pnl':pnl,'conf':p.get('conf'),'reason':reason},
                                    st['saldo']))
                del st['open'][sym]
            else:
                st['open'][sym]=p
        except Exception as e:
            log({'event':'err','symbol':sym,'msg':str(e)[:80]})
    return realized

def last_reason(sym, st):
    """Reasoning bos saat ENTRY (decision CONFIRMED) untuk symbol — bukan reject terakhir."""
    try:
        with open(LOG) as f:
            for line in reversed(f.readlines()[-400:]):
                e=json.loads(line)
                if e.get('event')=='decision' and e.get('symbol')==sym \
                   and e.get('decision')=='CONFIRMED' and (e.get('conf') or 0)>0:
                    return e.get('reason','')
    except Exception: pass
    return ''

def iterate(once=False):
    """Wrapper anti-race: cuma SATU proses boleh mutasi state (file-lock).
    Main loop = PRIORITAS: nunggu sampai 90 detik. Watchdog/cron = fallback: skip kalau sibuk."""
    import fcntl
    lk=acquire_lock(block_wait=90)
    if lk is None:
        return {'skipped':'locked_by_other_process'}
    try:
        return _iterate_inner(once)
    finally:
        try:
            fcntl.flock(lk,fcntl.LOCK_UN); lk.close()
        except Exception: pass

def _iterate_inner(once=False):
    st=load_state()
    k_cache={}
    # 1) kelola posisi terbuka dulu
    realized=manage_open(st,k_cache)
    # 2) kurir: cari kandidat baru di candle TERTUTUP terakhir
    n_open=len(st['open'])
    candidates=[]
    done={(d[0],d[1],d[2]) for d in st.get('done',[])}  # dedup: load SEKALI sebelum loop pair
    for sym in PAIRS:
        try:
            k5=vg.fetch_hist_klines(sym,'5m',600)
            k_cache[sym]=k5
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rb.rsi(c); zz=rb.zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            # mode HYBRID: fade + trend pullback (LLM gate tetap)
            maps=hr.build_htf_maps(sym,len(kk))
            htf15=[maps['15m'].get(kk[i][0]) for i in range(len(kk))]
            htf60=[maps['1h'].get(kk[i][0]) for i in range(len(kk))]
            sigs=hr.gen_hybrid(kk,rs,zz,vsma,htf15,htf60)
            # dedup via done-set (sym,bar_ts,side) — di-load sekali di atas, BUKAN per-pair reset
            for (si,side,grade) in sigs:
                i=si
                if i>=len(kk)-24:
                    key=(sym,kk[i][0],side)
                    if key in done: continue
                    if sym in st['open']: continue
                    if int(time.time()*1000)<st.get('cooldown',{}).get(sym,0): continue
                    o,h,l,cl=(kk[i][j] for j in (1,2,3,4))
                    rng=h-l
                    imb=((min(o,cl)-l)-(h-max(o,cl)))/rng if rng>0 else 0
                    score={'imb':round(imb,3),'vol_x':round(v[i]/vsma[i],2),
                           'z':round(zz[i],2),'rsi':round(rs[i],1)}
                    reg=rb.regime_1h(sym)
                    fund=fund_last(sym)
                    tvv=tv_ta(sym) if not once else None
                    brief=ds.build_briefing(sym,grade,side,score,reg,fund,tvv,True)
                    candidates.append({'sym':sym,'i':i,'side':side,'grade':grade,
                                       'brief':brief,'entry_next':float(kk[i+1][1]) if i+1<len(kk) else None,
                                       'regime':reg})
                    done.add(key)
        except Exception as e:
            log({'event':'err','symbol':sym,'msg':str(e)[:80]})
        st.setdefault('last_seen',{})[sym]=kk[-1][0]
    st['done']=[list(k) for k in list(done)[-600:]]  # persist dedup (cap 600)
    # 3) bos putuskan (batch, urut grade A dulu)
    candidates.sort(key=lambda x:(x['grade']!='A', x['sym']))
    confirmed=0
    for cd in candidates:
        d=llm_call(cd['brief'])
        log({'event':'decision','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade'],
             'decision':d.get('decision'),'conf':d.get('confidence'),
             'reason':d.get('reason'),'factor':d.get('key_factor')})
        save_state(st)  # persist done-list juga (dedup lintas restart)
        if d.get('decision')!='CONFIRMED': continue
        if n_open+confirmed>=og.MAX_GLOBAL_POSITIONS:
            log({'event':'skip_full','symbol':cd['sym']}); continue
        if LIVE:
            # EKSEKUSI NYATA: market order + SL/TP diembankan ke janitor order_guard
            if not og.API_KEY or not og.API_SECRET:
                log({'event':'LIVE_SKIP_NO_KEY','symbol':cd['sym']}); continue
            try:
                close_side='SELL' if side=='LONG' else 'BUY'
                # market order: qty dari notional (MARGIN*LEV), step-size disesuaikan simbol
                qty=round(MARGIN*LEV/entry, 3 if entry>=10 else (0 if entry>=100 else 1))
                og._req('POST','/fapi/v1/order',{'symbol':cd['sym'],'side':'BUY' if side=='LONG' else 'SELL',
                        'type':'MARKET','quantity':f'{qty}'})
                st_sl_tp=og.try_place_sl_tp(cd['sym'], side, sl, tp)
                og.targets[cd['sym']]={'side':side,'sl':sl,'tp':tp}
                if not (st_sl_tp['sl'] and st_sl_tp['tp']):
                    og.start_janitor({cd['sym']: og.targets[cd['sym']]})  # kejar sampai terpasang
                log({'event':'LIVE_ORDER','symbol':cd['sym'],'side':side,'qty':qty,
                     'sl':sl,'tp':tp,'sltp':st_sl_tp})
                reason=d.get('reason','') or d.get('key_factor','')
                tg.send(tg.fmt_open({'symbol':cd['sym'],'side':side,'grade':cd['grade'],
                             'entry':entry,'sl':sl,'tp':tp,'tp_rr':tp_rr,
                             'conf':d.get('confidence'),'reason':reason})+'\n🟢 <b>MODE LIVE</b> — order beneran terkirim')
                confirmed+=1
            except Exception as ex:
                log({'event':'LIVE_ERR','symbol':cd['sym'],'msg':str(ex)[:120]})
            continue
        entry=cd['entry_next']
        if entry is None: continue
        side=cd['side']
        # CHOP SNIPER: regime RANGE = TP 2:1 (cepat), hold pendek 8 jam; TREND = 3:1, hold 40 jam
        regime=cd.get('regime','RANGE')
        tp_rr=TP_RR_CHOP if regime=='RANGE' else TP_RR_TREND
        sl_d=entry*SL_PCT; tp_d=sl_d*tp_rr  # SL % dari harga (proporsional semua coin)
        sl=entry-sl_d if side=='LONG' else entry+sl_d
        tp=entry+tp_d if side=='LONG' else entry-tp_d
        st['open'][cd['sym']]={'side':side,'entry':entry,'sl':sl,'tp':tp,'be_moved':False,
                               'open_ts':int(time.time()*1000),'conf':d.get('confidence'),
                               'grade':cd['grade'],'regime':regime,'tp_rr':tp_rr}
        confirmed+=1
        reason=d.get('reason','') or d.get('key_factor','')
        log({'event':'open','symbol':cd['sym'],'side':side,'entry':entry,'sl':sl,'tp':tp,
             'conf':d.get('confidence'),'grade':cd['grade'],'reason':reason})
        tg.send(tg.fmt_open({'symbol':cd['sym'],'side':side,'grade':cd['grade'],
                             'entry':entry,'sl':sl,'tp':tp,'tp_rr':tp_rr,
                             'conf':d.get('confidence'),'reason':reason}))
        # save PER EVENT: kalau proses kena kill saat LLM error bertubi, keputusan gak ilang & gak diulang
        save_state(st)
    return {'realized':realized,'candidates':len(candidates),'confirmed':confirmed,
            'open_now':len(st['open'])}

def report_daily(send_tg=False):
    """Untuk cron: ringkasan 24 jam terakhir dari log."""
    import json as _j
    dayAgo=time.time()*1000-86400000
    dec=open_=ex=0; pnl=0.0; hits={}
    confs=[]; accepted=0
    for line in open(LOG):
        try: e=_j.loads(line)
        except Exception: continue
        t=e.get('ts','')
        try:
            ts=datetime.fromisoformat(t).timestamp()*1000
        except Exception: continue
        if ts<dayAgo: continue
        if e['event']=='decision':
            dec+=1
            if e.get('decision')=='CONFIRMED': accepted+=1; confs.append(e.get('conf') or 0)
        elif e['event']=='open': open_+=1
        elif e['event']=='exit':
            ex+=1; pnl+=e.get('pnl',0); hits[e['hit']]=hits.get(e['hit'],0)+1
    rep={'decisions':dec,'accepted':accepted,'open':open_,'exits':ex,
         'pnl_24h':round(pnl,2),'hits':hits,
         'avg_conf':round(sum(confs)/len(confs),1) if confs else 0}
    if send_tg:
        st=load_state()
        # sample reasoning terakhir utk briefing
        sample=[]
        try:
            for line in reversed(open(LOG).readlines()[-100:]):
                e=json.loads(line)
                if e.get('event')=='decision' and len(sample)<3: sample.append(e)
        except Exception: pass
        tg.send(tg.fmt_briefing(rep, st.get('open',{}), sample))
    return rep

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--pairs',default='ALL')
    ap.add_argument('--once',action='store_true')
    ap.add_argument('--report',action='store_true')
    ap.add_argument('--watch',action='store_true')
    ap.add_argument('--live',action='store_true')
    a=ap.parse_args()
    if a.live: LIVE=True
    # safety: kalau MODE=live tapi BINANCE key kosong -> paksa dry (jangan bunuh diri)
    if LIVE and not (os.environ.get('BINANCE_API_KEY') and os.environ.get('BINANCE_API_SECRET')):
        print('[SAFETY] MODE=live tapi BINANCE key kosong -> paksa DRY', flush=True)
        LIVE=False
    if a.report:
        print(json.dumps(report_daily(send_tg=True),indent=1))
    elif a.watch:
        # watchdog = fallback ONLY: jangan rebutan lock dgn main loop
        lk=acquire_lock()
        if lk is not None:
            try:
                st=load_state(); k_cache={}
                rl=manage_open(st,k_cache)
                save_state(st)
                print(json.dumps({'watch':1,'realized':rl,'open':len(st['open'])}))
            finally:
                try: fcntl.flock(lk,fcntl.LOCK_UN); lk.close()
                except Exception: pass
        else:
            print(json.dumps({'watch':0,'skipped':'locked'}))
    elif a.once:
        print(json.dumps(iterate(once=True),indent=1))
    else:
        print(f"[dewa-live] loop start pairs={len(PAIRS)} LIVE={LIVE}",flush=True)
        # startup notif: user harus liat bot online tiap kali restart
        try:
            from datetime import timezone as _tz, timedelta as _td
            wib=datetime.now(_tz(_td(hours=7))).strftime('%d %b %Y %H:%M:%S')
            st0=load_state()
            nopen=len(st0.get('open',{}))
            saldo0=st0.get('saldo',0)
            mode_tag="🟢 LIVE — ORDER BENERAN" if LIVE else "⚪ DRY RUN — virtual"
            lines=[f"🤖 BOT ONLINE — MODE HYBRID ({mode_tag})","━━━━━━━━━━━━━━━━━━",
                   f"⚙️ SL {SL_PCT*100:.1f}% | TP {TP_RR_TREND:.0f}R trend / {TP_RR_CHOP:.0f}R chop | Margin ${MARGIN*100:.0f} | BE {BE_TRIG*100:.1f}%",
                   "🔁 Scan kontinu 41 pair",
                   "🧠 Kurir: fade + trend pullback | Bos LLM gerbang terakhir",
                   "⏱️ Watchdog 20s | Max 5 posisi | Margin $2 x 10x",
                   f"🏦 Saldo net (virtual): {saldo0:+.2f} USD",
                   f"📂 Posisi terbuka: {nopen}",
                   f"⏰ {wib} WIB","━━━━━━━━━━━━━━━━━━",
                   "✅ Semua patch aktif. Notif selanjutnya = entry/exit asli."]
            tg.send("\n".join(lines))
        except Exception as e:
            print('startup_tg_err',repr(e),flush=True)
        while True:
            # WATCHDOG PROSES: iterasi HARUS selesai < 900 detik, kalau gagal bunuh diri (exit 99)
            # (240 terlalu ketat: 1 kandidat LLMerror = 2×(45+3)s = 96s)
            # supervisor (dewa_supervisor.sh) otomatis nyalain lagi dalam 5 detik
            import threading
            timer=threading.Timer(900, lambda: os._exit(99))
            timer.daemon=True
            try:
                timer.start()
                r=iterate()
                print(datetime.now(timezone.utc).strftime('%H:%M'), r, flush=True)
            except SystemExit: raise
            except Exception as e:
                print('ERR',repr(e),flush=True)
                r={'open_now':0}
            finally:
                timer.cancel()
            time.sleep(20 if r.get('open_now') else SCAN_SEC)  # ada posisi terbuka = pantau lebih rapat
