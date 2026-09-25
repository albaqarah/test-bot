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
import importlib.util, json, os, sys, time, argparse, subprocess, urllib.request
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
import tradfi_session as tfs

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
BE_TRIG=_cfg('BE_TRIG',0.0010)          # (mode TRAIL=off) shift BE kalau profit >= ini
BE_OFF=_cfg('BE_OFF',0.0006)            # (mode TRAIL=off) BE = entry +/- ini
TRAIL_ACT=_cfg('TRAIL_ACT',0.003)       # P10b: mulai ngunci profit saat mv >= ini
TRAIL_DIST=_cfg('TRAIL_DIST',0.002)     # P10b: SL mengunci sejauh ini di belakang ekstrem harga (trailing)
TRAIL=str(os.environ.get('TRAIL','on')).split('#',1)[0].strip().lower() in ('on','1','true','yes')  # P10b toggle (rollback: off)
MAXHOLD=_cfg('MAXHOLD_TREND',480,int)   # max hold bar 5m utk trend (480=40 jam)
MAXHOLD_CHOP=_cfg('MAXHOLD_CHOP',96,int)# max hold utk chop (96=8 jam)
COOLDOWN_MIN=_cfg('COOLDOWN_MIN',30,int)# re-entry cooldown per pair (menit)
SCAN_SEC=_cfg('SCAN_SEC',60,int)        # jeda antar scan (detik) saat idle
P6_LOOSE=os.environ.get('P6_LOOSE','off').strip().lower() in ('on','1','true','yes')  # P6 fade longgar (rollback: off)
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

def live_px(sym):
    """Harga live terakhir (ticker/price fapi, weight 1). None kalau gagal."""
    try:
        return float(json.loads(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}",timeout=8).read())['price'])
    except Exception:
        return None

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

BOS_PROVIDER=os.environ.get('BOS_PROVIDER','jev').strip().lower()   # 'jev' | 'lightvela' (.env)

def llm_call(brief):
    # P-jev: jev = bos utama (0.6 dtk, typed, no_json impossible); error -> fallback lightvela otomatis
    if BOS_PROVIDER=='jev':
        try:
            import jev_bridge
            r=jev_bridge.call_jev(brief)
            if r.get('decision') in ('CONFIRMED','REJECT'):
                return r
            raise RuntimeError('jev bad response')
        except Exception as e:
            log({'event':'jev_fallback','msg':str(e)[:100]})
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
            k5=k_cache.get(sym) or vg.fetch_hist_klines(sym,'5m',4)
            k_cache[sym]=k5
            # P10a: BE hanya baca bar CLOSED — bar forming menyertakan wick SEBELUM entry
            # (OPUSDT 05:52: high bar lama dihitung = "profit" palsu -> BE instan -> exit 28 dtk)
            _cut=int(time.time()*1000)-300000
            closed=[x for x in k5 if int(x[0])<_cut] or k5[-2:-1] or k5
            # wick gabungan bar closed TERAKHIR (yang belum pernah dinilai iterasi sebelumnya) utk BE-shift:
            lastc=closed[-1]
            last=k5[-1]  # bar forming utk SL/TP realtime & TIME exit (P10 hotfix)
            h,l=float(lastc[2]),float(lastc[3])
            fh,fl=float(last[2]),float(last[3])  # bar forming (live) utk trailing ekstrem & hit detection
            side=p['side']
            # === P10b: TRAILING PROFIT LOCK (konsep breakeven asli) ===
            # ekstrem harga TERCAPAI sepanjang posisi di-update dari bar closed (anti wick-palsu, P10a) + bar forming:
            # P10b-fix: scan SEMUA bar closed sejak posisi lahir (jangan cuma 1 bar) + bar forming
            _born=max(int(p['open_ts']),_cut)  # bar sebelum posisi lahir gak boleh dihitung
            for bx in k5:
                if int(bx[0])>=_born:
                    p['hi_px']=max(p.get('hi_px',p['entry']),float(bx[2]))
                    p['lo_px']=min(p.get('lo_px',p['entry']),float(bx[3]))
            p['hi_px']=max(p['hi_px'],fh); p['lo_px']=min(p['lo_px'],fl)
            if TRAIL:
                mv_top=(p['hi_px']-p['entry'])/p['entry']
                mv_bot=(p['entry']-p['lo_px'])/p['entry']
                if side=='LONG' and mv_top>=TRAIL_ACT:
                    new_sl=p['hi_px']*(1-TRAIL_DIST)
                    if new_sl>p['sl']: p['sl']=new_sl; p['be_moved']=True
                elif side=='SHORT' and mv_bot>=TRAIL_ACT:
                    new_sl=p['lo_px']*(1+TRAIL_DIST)
                    if new_sl<p['sl']: p['sl']=new_sl; p['be_moved']=True
            else:
                # mode BE lama (rollback): geser ke entry+fee — pakai ekstrem SEJAK posisi lahir (P10a)
                if not p['be_moved'] and now-p['open_ts']>=300000:
                    if side=='LONG' and p['hi_px']>=p['entry']*(1+BE_TRIG): p['be_moved']=True; p['sl']=p['entry']*(1+BE_OFF)
                    if side=='SHORT' and p['lo_px']<=p['entry']*(1-BE_TRIG): p['be_moved']=True; p['sl']=p['entry']*(1+BE_OFF)
            # SL/TP hit detection pakai bar FORMING (live) — SL/TP nyata kena realtime itu benar
            hit=None; exit_px=None
            def _lock_label(_sl):
                mv=( _sl-p['entry'])/p['entry']*(1 if side=='LONG' else -1)
                if mv>=2*FEE: return 'WIN-LOCK'   # profit beneran terkunci di atas fee
                if mv>0: return 'LOCK'            # terkunci tapi nyaris fee (jarak trail min)
                return 'BE' if p['be_moved'] else 'SL'
            if side=='LONG':
                if fl<=p['sl']: hit=_lock_label(p['sl']); exit_px=p['sl']
                elif fh>=p['tp']: hit='TP'; exit_px=p['tp']
            else:
                if fh>=p['sl']: hit=_lock_label(p['sl']); exit_px=p['sl']
                elif fl<=p['tp']: hit='TP'; exit_px=p['tp']
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
                save_state(st)  # P15-FIX: same — del dulu lalu save
                continue
            if hit:
                mv=(exit_px-p['entry'])/p['entry']*(1 if side=='LONG' else -1)
                fee=2*FEE if hit!='SL' else FEE+FEE  # SL full taker, lainnya maker-ish sim
                pnl=100*MARGIN*(mv*LEV-fee*LEV)
                realized.append({'sym':sym,'hit':hit,'pnl':round(pnl,2),'bars':round(bars_open,1),
                                 'conf':p.get('conf'),'grade':p.get('grade'),'side':side})
                log({'event':'exit','symbol':sym,'hit':hit,'pnl':pnl,'conf':p.get('conf'),
                     'exit_px':exit_px,'sl':p['sl'],'entry':p['entry'],'hi':p.get('hi_px'),'lo':p.get('lo_px')})
                st['saldo']=round(st.get('saldo',0)+pnl,2)
                # cooldown: jangan re-entry pair yg baru exit dalam 30 menit (anti duplikasi)
                st.setdefault('cooldown',{})[sym]=now+COOLDOWN_MS
                # poin 4: pastikan ga ada SL/TP nyantol setelah close
                oc.cleanup_leftovers(sym, live=og.API_KEY and og.API_SECRET and LIVE)
                # poin 2: notifikasi Telegram (win/lose + saldo net + reasoning)
                reason=last_reason(sym, st)
                tg.send(tg.fmt_exit({'symbol':sym,'side':p.get('side'),'hit':hit,
                                     'pnl':pnl,'conf':p.get('conf'),'reason':reason,
                                     'exit_px':exit_px,'sl':p['sl'],'entry':p['entry'],
                                     'bars':round(bars_open,1)},
                                    st['saldo'], n_open=len(st['open'])-1))
                del st['open'][sym]  # P15-FIX: del DULU baru save — dulu save dgn posisi masih open
                save_state(st)       # → iterasi berikut load posisi balik → exit dobel (bug SUI 4×)
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
    if realized and st.get('full_warned') and len(st['open'])<og.MAX_GLOBAL_POSITIONS:
        st['full_warned']=False  # slot bebas -> boleh notif penuh lagi nanti
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
            sigs=hr.gen_hybrid(kk,rs,zz,vsma,htf15,htf60,
                               extra_engines='all' if P6_LOOSE else 'scalp')
            # dedup via done-set (sym,bar_ts,side) — di-load sekali di atas, BUKAN per-pair reset
            for (si,side,grade,src) in sigs:
                i=si
                # FRESHNESS: sinyal scalp harus muda (<=4 bar = 20 mnt) — sinyal tua = bangkai,
                # bikin backlog LLM 30-45 dtk/keputusan numpuk (scalper gak nunggu 90 mnt)
                if src=='scalp' and i<len(kk)-5: continue
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
                    try: extras=ds.build_extras(sym,kk,rs)
                    except Exception: extras=None
                    brief=ds.build_briefing(sym,grade,side,score,reg,fund,tvv,True,extras=extras,source=src)
                    # P13 VISION: suntik chart RSI6 + momentum_class + bar detail ke briefing bos
                    try: brief=ds.enrich_briefing(brief,kk,rs)
                    except Exception: pass
                    # P16-C: RSI6 REALTIME — bos harus menilai kondisi yang SAMA dgn layar user.
                    # Bar closed telad (ARB: kurir lihat RSI6 83.4, user lihat 95.7). Ganti close terakhir
                    # dgn harga live → RSI6 sintetis "sekarang".
                    try:
                        _px=live_px(sym)
                        if _px:
                            _c=[float(r[4]) for r in kk[-20:]]
                            _c[-1]=_px
                            _r6rt=hr.rsi6(_c)[-1]
                            brief.setdefault('vision',{})['rsi6_now']=round(_r6rt,1)
                            brief['vision']['rsi6_source']='realtime'
                    except Exception: pass
                    # P13 KURIR GATE: momen 'kering' (tanpa aliran) dibuang SEBELUM bos — hemat API + anti sinyal sampah
                    vcls=str(brief.get('vision',{}).get('momentum_class',''))
                    if vcls=='kering':
                        log({'event':'skip_dry_momentum','symbol':sym,'side':side,'vol_x':score.get('vol_x')})
                        continue
                    # P14 TRADFI GATE: XAU/XAG/XPT/PAXG entry HANYA saat CME session OPEN (persis v15)
                    if sym in tfs.TRADFI and not tfs.tradfi_open():
                        log({'event':'skip_tradfi_closed','symbol':sym,'side':side,'session':tfs.tradfi_label()[0]})
                        continue
                    candidates.append({'sym':sym,'i':i,'side':side,'grade':grade,'key':key,'src':src,
                                       'brief':brief,'entry_next':float(kk[i+1][1]) if i+1<len(kk) else None,
                                       'regime':reg,'mclass':vcls})
                    done.add(key)
        except Exception as e:
            log({'event':'err','symbol':sym,'msg':str(e)[:80]})
        st.setdefault('last_seen',{})[sym]=kk[-1][0]
    st['done']=[list(k) for k in list(done)[-600:]]  # persist dedup (cap 600)
    # 3) bos putuskan (batch, urut grade A dulu)
    candidates.sort(key=lambda x:(x['grade']!='A', x['sym']))
    confirmed=0
    # GATE HEMAT-API (user): posisi penuh 5/5 -> kurir DILARANG nanya bos LLM. Notif sekali per kejadian.
    if candidates and n_open>=og.MAX_GLOBAL_POSITIONS:
        log({'event':'skip_full_position','n_open':n_open,'candidates':len(candidates)})
        if not st.get('full_warned'):
            log({'event':'positions_full','msg':'STOP, POSISI MASIH PENUH! TUNGGU SAMPAI ADA POSISI YG CLOSE DULU!',
                 'n_open':n_open,'candidates':len(candidates)})   # user: cukup di logs, jangan spam TG
            st['full_warned']=True
    for cd in candidates:
        if n_open>=og.MAX_GLOBAL_POSITIONS:
            log({'event':'skip_full_position','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade']})
            done.discard(cd['key'])  # jangan dikunci done — kalau slot buka lagi, sinyal bisa dinilai ulang
            continue
        d=llm_call(cd['brief'])
        # P17: MIN_CONF gate — conf skrg = p(total CONFIRMED*). Sinyal di bawah ambang = REJECT
        # (kandidat TIDAK dikunci done — kalau bos nanti lebih yakin di iterasi lain, boleh dinilai ulang)
        try: _minconf=float(os.environ.get('MIN_CONF','55'))
        except Exception: _minconf=55.0
        if d.get('decision')=='CONFIRMED' and float(d.get('confidence',0))<_minconf:
            d={'decision':'REJECT','confidence':d.get('confidence'),
               'reason':str(d.get('reason',''))+f" [MIN_CONF gate: {d.get('confidence')} < {_minconf}]",
               'key_factor':d.get('key_factor')}
        # P9 NORMALISASI SIDE: kurir ngirim 'L'/'S', seluruh jalur mutasi pakai 'LONG'/'SHORT'.
        # 'L' != 'LONG' bikin SL/TP kebalik (bug BCH 21:51 WIB: LONG kena SL palsu di profit)
        _side=cd['side']
        cd['side']={'L':'LONG','S':'SHORT'}.get(_side,_side)
        log({'event':'decision','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade'],
             'decision':d.get('decision'),'conf':d.get('confidence'),
             'reason':d.get('reason'),'factor':d.get('key_factor')})
        if d.get('decision') not in ('CONFIRMED','REJECT'):
            # llm_err/gateway mati: JANGAN dedup permanen — lepas dari done supaya iterasi
            # berikutnya nanya lagi ke bos (bug UNI-A 20:40 WIB: grade A hilang selamanya)
            done.discard(cd.get('key'))
            st['done']=[list(k) for k in list(done)[-600:]]
            log({'event':'retry_later','symbol':cd['sym'],'msg':'llm_err -> kandidat diulang iterasi berikut'})
        save_state(st)  # persist done-list juga (dedup lintas restart)
        if d.get('decision')!='CONFIRMED': continue
        # P16-B: WICK-EXTREME FLIP — bos dilarang ACC searah wick ekstrem. Kalau sinyal LONG datang
        # pas RSI6 realtime > 90 (pucuk), bos membalik jadi SHORT (peluang valid fade). Mirror SHORT < 10 → LONG.
        # (kasus ARB 21:35 WIB: breakout LONG di RSI6 83.4 → nyentuh 95.7 saat entry → langsung dibanting -0.8%)
        _v=(cd.get('brief') or {}).get('vision',{}) if isinstance(cd.get('brief'),dict) else {}
        _r6rt=_v.get('rsi6_now'); _mcl=_v.get('momentum_class','')
        _flipped=False
        try:
            _r6f=float(_r6rt) if _r6rt is not None else None
        except Exception: _r6f=None
        _old_side=cd['side']
        if _r6f is not None and _old_side=='LONG' and (_r6f>90 or (_mcl=='wick_extreme' and _r6f>80)):
            cd['side']='SHORT'; _flipped=True
        elif _r6f is not None and _old_side=='SHORT' and (_r6f<10 or (_mcl=='wick_extreme' and _r6f<20)):
            cd['side']='LONG'; _flipped=True
        if _flipped:
            reason=(d.get('reason','') or '')+f' [WICK-FLIP: sinyal dibalik — RSI6 realtime {_r6f} ekstrem, arah lama searah wick]'
            d['reason']=reason
            log({'event':'wick_flip','symbol':cd['sym'],'rsi6':_r6f,'mclass':_mcl,
                 'old_side':_old_side,'new_side':cd['side']})
        if n_open+confirmed>=og.MAX_GLOBAL_POSITIONS:
            log({'event':'skip_full','symbol':cd['sym']}); continue
        # P9 RESTRUKTURISASI: hitung entry/side/SL/TP SEBELUM cabang LIVE/dry.
        # Dulu: branch LIVE memakai side/entry/sl/tp dari kandidat SEBELUMNYA (undefined di iterasi pertama)
        side=cd['side']
        entry=cd['entry_next']
        # P9 ENTRY-REFRESH: antre LLM 27-45 dtk bikin open-candle basi (BCH: 330.19 vs live 339.57 = telad 2.8%).
        try:
            px=live_px(cd['sym'])
            if px and px>0: entry=px
            else:
                log({'event':'skip_stale','symbol':cd['sym'],'msg':'harga live gak valid'}); continue
        except Exception:
            log({'event':'skip_stale','symbol':cd['sym'],'msg':'gagal fetch harga live utk entry refresh'}); continue
        # RE-CHECK tepat sebelum mutasi: selama tunggu LLM (27-45s/kandidat), dunia bisa berubah
        if cd['sym'] in st['open']:
            log({'event':'skip_open','symbol':cd['sym'],'msg':'posisi sudah ada (re-check pre-mutasi)'}); continue
        # P1 COOLDOWN di titik mutasi (dulu cuma dicek saat scan): anti re-entry 100 detik pasca-SL
        if int(time.time()*1000) < st.get('cooldown',{}).get(cd['sym'],0):
            log({'event':'skip_cooldown','symbol':cd['sym'],'msg':'cooldown aktif (re-check di mutasi)'}); continue
        # CHOP SNIPER: regime RANGE = TP cepat, hold pendek; TREND = RR panjang
        regime=cd.get('regime','RANGE')
        tp_rr=TP_RR_CHOP if regime=='RANGE' else TP_RR_TREND
        sl_pct=SL_PCT
        # P11: BOS YANG MIKIRIN SL/TP (varian eksekusi dari jev) — guard tetap ketat:
        variant=str(d.get('variant','')).upper() if isinstance(d,dict) else ''
        if variant=='TIGHT':   sl_pct, tp_rr = SL_PCT*0.67, 2.5   # momentum jelas: SL 0.8%, TP 1:2.5
        elif variant=='WIDE':  sl_pct, tp_rr = SL_PCT*1.5, 4.0    # wick besar: SL 1.8%, TP 1:4 (di balik struktur)
        # P19 RANGE-POSITION GUARD: SL yang jatuh DI DALAM range 6 jam (72 bar) gampang kena noise/wick.
        # Kasus RUNE 25 Sep 08:01 WIB: LONG @0.6402, SL 1.2% = 0.6325 — cuma 0.06% di atas low range
        # 0.6319 → wick ke low range aja cukup memotong (dan benar terjadi). Solusi: kalau level SL
        # berada di dalam range → SL dipaksa WIDE (1.8%) sampai keluar dr tepi range. Best-effort.
        try:
            _kc=k_cache.get(cd['sym']) or []
            if len(_kc)<73:
                _hi=_lo=None
            else:
                _hi=max(float(b[2]) for b in _kc[-72:]); _lo=min(float(b[3]) for b in _kc[-72:])
            if _hi>_lo:
                _pos=(entry-_lo)/(_hi-_lo)
                # SL efektif berada DI DALAM range = pasti bisa kena noise range biasa (kasus RUNE:
                # SL 0.6325 > low 0.6319 — cukup wick ke low range untuk memotong).
                _sl_in_range = entry*(1-SL_PCT) > _lo if side=='LONG' else entry*(1+SL_PCT) < _hi
                if side=='LONG' and _sl_in_range and variant!='WIDE':
                    sl_pct, tp_rr = SL_PCT*1.5, 4.0
                    log({'event':'range_guard_wide','symbol':cd['sym'],'side':side,
                         'pos_in_range':round(_pos,2),'range_hi':_hi,'range_lo':_lo,
                         'msg':'LONG deket resistance 6-jam — SL di-WIDE-in'})
                elif side=='SHORT' and entry*(1+SL_PCT) < _hi and variant!='WIDE':
                    sl_pct, tp_rr = SL_PCT*1.5, 4.0
                    log({'event':'range_guard_wide','symbol':cd['sym'],'side':side,
                         'pos_in_range':round(_pos,2),'range_hi':_hi,'range_lo':_lo,
                         'msg':'SHORT deket support 6-jam — SL di-WIDE-in'})
        except Exception:
            pass  # guard best-effort; kag gagal = perilaku lama
        # NORMAL / tanpa varian = angka engine (SL_PCT & RR regime) — fallback selalu ada
        sl_d=entry*sl_pct; tp_d=sl_d*tp_rr  # SL % dari harga (proporsional semua coin)
        sl=entry-sl_d if side=='LONG' else entry+sl_d
        tp=entry+tp_d if side=='LONG' else entry-tp_d
        if LIVE:
            # EKSEKUSI NYATA: market order + SL/TP diembankan ke janitor order_guard
            if not og.API_KEY or not og.API_SECRET:
                log({'event':'LIVE_SKIP_NO_KEY','symbol':cd['sym']}); continue
            try:
                close_side='SELL' if side=='LONG' else 'BUY'
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
                             'entry':entry,'sl':sl,'tp':tp,'tp_rr':tp_rr,'qty':qty,
                             'conf':d.get('confidence'),'reason':reason})+'\n🟢 <b>MODE LIVE</b> — order beneran terkirim')
                confirmed+=1
            except Exception as ex:
                log({'event':'LIVE_ERR','symbol':cd['sym'],'msg':str(ex)[:120]})
            continue
        st['open'][cd['sym']]={'side':side,'entry':entry,'sl':sl,'tp':tp,'be_moved':False,
                               'open_ts':int(time.time()*1000),'conf':d.get('confidence'),
                               'hi_px':entry,'lo_px':entry,
                               'grade':cd['grade'],'regime':regime,'tp_rr':tp_rr}
        confirmed+=1
        reason=d.get('reason','') or d.get('key_factor','')
        log({'event':'open','symbol':cd['sym'],'side':side,'entry':entry,'sl':sl,'tp':tp,
             'conf':d.get('confidence'),'grade':cd['grade'],'reason':reason})
        _v=(cd.get('brief') or {}).get('vision',{}) if isinstance(cd.get('brief'),dict) else {}
        tg.send(tg.fmt_open({'symbol':cd['sym'],'side':side,'grade':cd['grade'],
                             'entry':entry,'sl':sl,'tp':tp,'tp_rr':tp_rr,
                             'qty':round(20.0/entry,6),
                             'conf':d.get('confidence'),'reason':reason,
                             'variant':str(d.get('variant','')).upper(),
                             'regime':regime,'mclass':_v.get('momentum_class'),
                             'rsi6':_v.get('rsi6_now'),
                             'n_open':len(st['open']),'saldo':st.get('saldo',0)}))
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
        # P18-fix: marker ditulis SETELAH briefing dihitung & dikirim — briefing selalu
        # merekap 24 jam penuh, notif sesudahnya mulai dari 0.
        st=load_state()
        # sample reasoning terakhir utk briefing
        sample=[]
        try:
            for line in reversed(open(LOG).readlines()[-100:]):
                e=json.loads(line)
                if e.get('event')=='decision' and len(sample)<3: sample.append(e)
        except Exception: pass
        tg.send(tg.fmt_briefing(rep, st.get('open',{}), sample))
        # P18-fix: marker SETELAH kirim → notif berikutnya reset 0/0, briefing tetap 24 jam penuh
        open('/home/agentuser/.dewa_briefing_mark','w').write(time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()))
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
        # anti-double-iterator: kalau lock sudah dipegang proses lain saat boot, jangan perang
        import fcntl as _f
        _probe=open(LOCKF,'w')
        try:
            _f.flock(_probe,_f.LOCK_EX|_f.LOCK_NB)
            _f.flock(_probe,_f.LOCK_UN)
        except BlockingIOError:
            print('[dewa-live] BOOT: lock dipegang proses lain -> exit (penjaga sudah ada)',flush=True)
            os._exit(0)
        _probe.close()
        print(f"[dewa-live] loop start pairs={len(PAIRS)} LIVE={LIVE}",flush=True)
        # startup notif: user harus liat bot online tiap kali restart
        try:
            from datetime import timezone as _tz, timedelta as _td
            wib=datetime.now(_tz(_td(hours=7))).strftime('%d %b %Y %H:%M:%S')
            st0=load_state()
            nopen=len(st0.get('open',{}))
            saldo0=st0.get('saldo',0)
            mode_tag="🟢 LIVE — ORDER BENERAN" if LIVE else "⚪ DRY RUN — virtual"
            tg.send(tg.fmt_start(saldo0, n_open=nopen))
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
