#!/usr/bin/env python3
"""
dewa_live.py — BOT LIVE FINAL v7.0 (dry-run mode default: eksekusi virtual).
Pipeline v7.0: Data -> KURIR v7 (3 engine preset + HIGHER TF FILTER) -> payload JSON
-> BOS jev persona v7.0 (pipeline P1-P8, tanpa rubric) -> Risk gate (max 5 posisi)
-> Eksekusi virtual (SL/TP varian, ATR murni v10.0) -> Janitor SL/TP + trail-lock P10b.

Usage: python3 dewa_live.py --pairs ALL --once   (1 iterasi, untuk cron)
       python3 dewa_live.py --pairs ALL          (loop terus)
       python3 dewa_live.py --live               (EKSEKUSI BENERAN — butuh API key, default OFF)
"""
import importlib.util, json, os, sys, time, argparse, urllib.request
from datetime import datetime, timezone

def _load_env(path=None):
    """P35b: baca .env dgn OVERRIDE PENUH (bukan setdefault).
    Alasan: pernah kejadian env warisan shell/PM2 (JEV_API_KEY dummy dari unit test) MENANG
    atas .env -> bot 401/402 nggak jelas. .env = sumber kebenaran, selalu menang."""
    path=path or os.path.join(os.path.dirname(os.path.abspath(__file__)),'.env')
    try:
        for line in open(path):
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1)
                os.environ[k.strip()]=v.strip()
    except Exception: pass
_load_env()

spec=importlib.util.spec_from_file_location('vg',os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15_grade.py'))
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
import reversion_bot as rb
import gmv2  # v12.2 GODMODE sensor (port v15-pro-genius, stdlib)
import dewa_skill as ds  # v7.0: build_payload_v7 (kontrak JSON bos) + btc_bias (macro)
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
TRAIL_ACT=_cfg('TRAIL_ACT',0.003)       # P10b: mulai ngunci profit saat mv >= ini
TRAIL_DIST=_cfg('TRAIL_DIST',0.002)     # P10b: SL mengunci sejauh ini di belakang ekstrem harga (trailing)
TRAIL=str(os.environ.get('TRAIL','on')).split('#',1)[0].strip().lower() in ('on','1','true','yes')  # P10b toggle
MAXHOLD=_cfg('MAXHOLD_TREND',480,int)   # max hold bar 5m utk trend (480=40 jam)
MAXHOLD_CHOP=_cfg('MAXHOLD_CHOP',96,int)# max hold utk chop (96=8 jam)
COOLDOWN_MIN=_cfg('COOLDOWN_MIN',30,int)# re-entry cooldown per pair (menit)
SCAN_SEC=_cfg('SCAN_SEC',60,int)        # jeda antar scan (detik) saat idle
COOLDOWN_MS=COOLDOWN_MIN*60*1000
LIVE=os.environ.get('MODE','dry').strip().lower()=='live'   # MODE=live di .env -> eksekusi nyata

LOG=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live_log.jsonl')
STATE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live_state.json')
LOCKF=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live.lock')
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

def smc_btc_volume():
    """v9.0 Super Money Flow: rasio volume 3-bar terakhir BTC vs SMA20 — suntikan dana pasar.
    None kalau data gagal (fail-open: kurir jalan normal tanpa sinyal superflow)."""
    try:
        kk=fetch_hist_klines('BTCUSDT','5m',25)
        v=[float(x[5]) for x in kk]
        vma=sum(v[-23:-3])/20 or 1e-9
        return round(sum(v[-3:])/(3*vma),2)
    except Exception:
        return None


def fund_last(sym):
    try:
        import urllib.request
        d=json.loads(urllib.request.urlopen(
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1",timeout=8).read())
        return float(d[0]['fundingRate'])
    except Exception: return 0.0

# v7.0: tv_ta/TradingView bridge DIHAPUS — HTF 15m/1h sekarang dari Binance klines langsung (kurir v7 build_htf_maps)

# v7.0: FULL JEV NO-FALLBACK (P35) — bos = jev_bridge.call_jev, persona v7.0; tanpa model kedua

def llm_call(brief):
    # P35 FULL JEV NO-FALLBACK (komando user 29 Sep): model cadangan DIHAPUS TOTAL.
    # jev error sesaat (timeout/429/5xx) = kandidat ini dilewati, kandidat BERIKUTNYA dinilai normal;
    # state scan/sistem gak terpengaruh — diulang alami di iterasi berikutnya.
    # 402 = notif topup (anti-spam 1x/jam). GAK ADA model kedua, GAK ADA istirahat panjang.
    import jev_bridge
    try:
        r=jev_bridge.call_jev(brief)
        if r.get('decision') in ('CONFIRMED','REJECT'):
            return r
        raise RuntimeError('jev bad response')
    except Exception as e:
        _is402=jev402_hit(e)
        log({'event':('jev_402' if _is402 else 'jev_err'),'msg':str(e)[:100]})
        if _is402: _notify_bos_down('402', str(e))
        return {"decision":"REJECT","confidence":0,"reason":f"jev_err:{str(e)[:60]}"}

def jev402_hit(e):
    """True kalau exception = HTTP 402 Payment Required (quota habis -> ganti provider)."""
    try:
        import jev_bridge as _jb
        if isinstance(e, _jb.Jev402): return True
    except Exception:
        pass
    s=str(e)
    return '402' in s or 'Payment Required' in s

def _notify_bos_down(kind, detail=''):
    """P35: notif TG 402 — FULL JEV, tanpa fallback. Max 1x/jam (P33 anti-spam,
    flag file terpisah dewa_notify_flag.json)."""
    try:
        flagf=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_notify_flag.json')
        now=time.time()
        try: flags=json.load(open(flagf))
        except Exception: flags={}
        key=f'bos_down_{kind}'
        if now-flags.get(key,0) < 3600: return
        flags[key]=now
        json.dump(flags, open(flagf,'w'))
        bot_provider='jev'
        head=f"⚠️ BOS JEV 402 — BUTUH TOPUP"
        tg.send(
            f"{head}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%d %b %H:%M UTC')}\n"
            f"🤖 Bos      : jev (HTTP 402 Payment Required)\n"
            f"🔗 Detail   : {detail[:90]}\n"
            f"➡️ Status   : FULL JEV — keputusan DITUNDA sampai topup (jev satu-satunya bos)\n"
            f"🔁 Retry 429: otomatis 3 detik (aktif)\n"
            f"🛡️ Loop     : scan tetap hidup, kandidat diulang iterasi berikutnya")
    except Exception as e:
        log({'event':'notify_bos_down_err','msg':str(e)[:80]})

def manage_open(st, k_cache):
    """Update posisi virtual: BE-shift, SL/TP hit, max-hold. Return realized pnl list."""
    realized=[]
    now=int(time.time()*1000)
    for sym in list(st['open'].keys()):
        p=st['open'][sym]
        # === P23: TRADFI FORCE-FLAT — posisi logam/PAXG dipaksa cair 2 jam sebelum break/close ===
        if sym in tfs.TRADFI:
            try:
                _eb,_ff,_why=tfs.tradfi_window()
                if _ff:
                    if p.get('tradfi_eod_done'):   # P23 anti-dobel (race restart)
                        continue
                    p['tradfi_eod_done']=True
                    exit_px=live_px(sym) or p['entry']
                    qty=p.get('qty') or (MARGIN*100*LEV)/p['entry']   # v7.1.1 #2: notional dinamis (dulu hardcode 20.0)
                    side=p['side']
                    pnl=(exit_px-p['entry'])*qty*(1 if side=='LONG' else -1)
                    pnl=round(pnl-0.02,2)  # fee taker
                    st['saldo']=round(st.get('saldo',0)+pnl,2)
                    log({'event':'exit','symbol':sym,'hit':'TRADFI_EOD','pnl':pnl,'conf':p.get('conf'),
                         'live':True,'reason':f'force-flat {_why}'})
                    tg.send(tg.fmt_exit({'symbol':sym,'side':side,'hit':'TIME',
                                         'pnl':pnl,'conf':p.get('conf'),
                                         'reason':f'tradfi_eod ({_why})','entry':p['entry'],
                                         'exit_px':exit_px,'bars':round((now-int(p["open_ts"]))/300000)},
                                        st['saldo'], n_open=len(st['open'])-1))
                    og.targets.pop(sym,None)
                    del st['open'][sym]   # urutan suci: del -> save
                    save_state(st)
                    st.setdefault('cooldown',{})[sym]=now+COOLDOWN_MS
                    realized.append({'sym':sym,'hit':'TRADFI_EOD','pnl':pnl,'bars':0,
                                     'conf':p.get('conf'),'grade':p.get('grade'),'side':side})
                    continue
            except Exception as _e:
                log({'event':'tradfi_ff_err','msg':str(_e)[:80]})
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
            # v7.0: mode BE lama (rollback P10) DIHAPUS — trail-lock P10b satu-satunya pengunci profit
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
            if sym in tfs.TRADFI: maxhold=min(maxhold,48)  # P23: TradFi max 4 jam — jangan nahan floating dlm market tipis
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

# v7.0: gate _p38_dry_pass DIHAPUS — filter mutu sekarang di SUMBER (kurir v7 3 engine + HTF), bos menilai semua lolosan

def _p39_trim(done, cap=2000):
    """P39 BUGFIX (ACC 30 Sep): trim done by bar_ts TERBARU.
    Dulu list(done)[-600:] — done itu SET, urutan list()-nya ARBITRARY (hash-based,
    bukan insertion/time) -> kunci BARU ikut kebuang tiap trim (bukti: AAVE:S nanya
    bos 11x/11 menit, key-nya gak ada di done; done selalu penuh pas 600)."""
    return [list(k) for k in sorted(done, key=lambda k: k[1])[-cap:]]

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
    pending_sides=set()  # v7.1.1 #1: dedup intra-batch (sym,side) — 1 pasangan 1 panggilan bos per batch
    done={(d[0],d[1],d[2]) for d in st.get('done',[])}  # dedup: load SEKALI sebelum loop pair
    for sym in PAIRS:
        try:
            k5=vg.fetch_hist_klines(sym,'5m',600)
            k_cache[sym]=k5
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rb.rsi6(c)   # P29: RSI6 TOTAL - satu-satunya RSI di pipeline
            zz=rb.zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            # ===== KURIR v7.0: 3 engine preset + HIGHER TF FILTER (Anti-Trap) =====
            maps=hr.build_htf_maps(sym,len(kk))
            kts=[r[0] for r in kk]
            htf15=hr.align_htf(kts, maps['15m'])   # forward-fill: bar 15m terakhir utk tiap 5m
            btcv=smc_btc_volume()  # v9.0 Super Money Flow: volume 3-bar BTC utk kurir
            sigs=hr.gen_hybrid(kk,rs,zz,vsma,htf15,maps['1h_struct'],btcv=btcv)  # v11.0 FIX: dulu positional jatuh ke slot extra_engines (mati) — SuperFlow hidup
            # dedup via done-set (sym,bar_ts,side) — di-load sekali di atas, BUKAN per-pair reset
            for (si,side,grade,src) in sigs:
                i=si
                # FRESHNESS: sinyal harus muda (<=4 bar = 20 mnt) — sinyal tua = bangkai
                if i<len(kk)-5: continue
                if i>=len(kk)-24:
                    key=(sym,kk[i][0],side)
                    if key in done: continue
                    if int(time.time()*1000)<st.get('reject_cd',{}).get(sym+':'+side,0): continue
                    if sym in st['open']: continue
                    if int(time.time()*1000)<st.get('cooldown',{}).get(sym,0): continue
                    reg=rb.regime_1h(sym)
                    fund=fund_last(sym)
                    brief=ds.build_payload_v7(sym,kk,side,grade,src,reg,fund,maps)
                    # v7.0 PAYLOAD KONTRAK (user-spec): macro + smc + metrics + market + slSuggest.
                    # P16-C RSI6 realtime (sama dgn layar user) + SMC + snapshot — semua best-effort.
                    try:
                        import smc_engine as _smc
                        brief.update(_smc.enrich(sym, ds.btc_bias()['bias']))
                    except Exception: pass
                    try:
                        import market_snapshot as _mkt
                        _mkt.enrich_market(brief, sym, kk, rs, i=i)   # v7.1: entryLoc diukur di bar kandidat
                        if brief.get('wickHint') and brief['wickHint'].get('dir')!='NONE':
                            log({'event':'wick_hint','symbol':sym,'side':side,
                                 'hint':brief['wickHint'].get('dir'),
                                 'pattern':brief['wickHint'].get('pattern'),
                                 'strength':brief['wickHint'].get('strength')})
                    except Exception: pass
                    try:
                        _px=live_px(sym)
                        if _px:
                            # v12.3 FIX SILENT-KILL: elemen terakhir WAJIB float (_px), dulu [[0,0,0,0,_px,0]]
                            # (list nyempul) -> TypeError -> except:pass -> lensa RSI6 live MATI TOTAL di produksi.
                            # 60-bar (bukan 19) + tick live = selaras dgn seri rules (rs dari 600 bar).
                            brief.setdefault('metrics',{})['rsi6Realtime']=round(
                                rb.rsi6([float(r[4]) for r in kk[-60:]]+[_px])[-1],1)
                    except Exception: pass
                    # v7.1 ANTI-CHASE DATA PLUMBING: entryLoc (host, gratis) -> metrics kontrak bos.
                    # Bos P5 (ANTI-CHASE COMPILER GUARD) WAJIB REJECT + WAIT_FOR_RETRACE_TO_FVG
                    # saat entryStatus=CHASE / atrDistance > 3.0.
                    try:
                        _el=brief.get('entryLoc') or {}
                        if _el.get('loc'):
                            brief.setdefault('metrics',{})['entryStatus']=str(_el['loc']).upper()
                            brief['metrics']['atrDistance']=_el.get('swing_dist_atr')
                            brief['metrics']['swingAgeBars']=_el.get('swing_age_bars')
                    except Exception: pass
                    # ===== v12.2 GODMODE SENSOR (port v15-pro-genius/godmode_v2_engine, stdlib) =====
                    # FeatureEngine + GodModeScorer: skor kuantitatif 0-100 utk ARAH SINYAL
                    # (trend/momentum/mtf/liquidity/volume/volatility/session + tier SNIPER/EXECUTE/
                    # WATCH/REJECT). Bot TETAP bosnya jev — GM cuma kompas tambahan di payload.godmode.
                    try:
                        _gmr=gmv2.evaluate(kk[:i+1], maps.get('c15'), 'LONG' if side=='L' else 'SHORT', rs[:i+1])
                        if _gmr:
                            brief['godmode']={'score':_gmr['score'],'tier':_gmr['tier'],
                                'setup':_gmr['setup'],'breakdown':_gmr['breakdown'],'line':_gmr['line']}
                            log({'event':'gm_score','symbol':sym,'side':side,
                                 'score':_gmr['score'],'tier':_gmr['tier'],'setup':_gmr['setup']})
                    except Exception as _gme:
                        log({'event':'gm_err','symbol':sym,'msg':str(_gme)[:80]})
                    # P14 TRADFI GATE: blok entry 3 jam sebelum break/close (anti volume kopong)
                    if sym in tfs.TRADFI:
                        _eb,_ff,_why=tfs.tradfi_window()
                        if _eb:
                            log({'event':'skip_tradfi_window','symbol':sym,'side':side,'window':_why})
                            continue
                    # v7.1.1 #1: dedup intra-batch — sinyal dobel (sym,side) di batch sama
                    # cuma diambil SEKALI (bar terbaru = loop urut), hemat kuota jev.
                    _ps=(sym,side)
                    if _ps in pending_sides: continue
                    pending_sides.add(_ps)
                    candidates.append({'sym':sym,'i':i,'side':side,'grade':grade,'key':key,'src':src,
                                       'brief':brief,'entry_next':float(kk[i+1][1]) if i+1<len(kk) else None,
                                       'regime':reg})
                    done.add(key)
        except Exception as e:
            log({'event':'err','symbol':sym,'msg':str(e)[:80]})
        st.setdefault('last_seen',{})[sym]=kk[-1][0]
    st['done']=_p39_trim(done)  # persist dedup (P39: trim by bar_ts, cap 2000)
    # 3) bos putuskan (batch, urut grade A dulu)
    candidates.sort(key=lambda x:(x['grade'] not in ('A','A+'), x['sym']))  # A+/A dulu (v11.0)
    confirmed=0
    # GATE HEMAT-API (user): posisi penuh 5/5 -> kurir DILARANG nanya bos LLM. Notif sekali per kejadian.
    if candidates and n_open>=og.MAX_GLOBAL_POSITIONS:
        log({'event':'skip_full_position','n_open':n_open,'candidates':len(candidates)})
        if not st.get('full_warned'):
            log({'event':'positions_full','msg':'STOP, POSISI MASIH PENUH! TUNGGU SAMPAI ADA POSISI YG CLOSE DULU!',
                 'n_open':n_open,'candidates':len(candidates)})   # user: cukup di logs, jangan spam TG
            st['full_warned']=True
    for cd in candidates:
        # ===== v12.3 FRESH RE-CHECK: sinyal dievaluasi ulang di DATA LIVE sebelum nanya bos =====
        # Audit 2 Okt: bar sinyal bisa basi saat eksekusi (trio 11:26 WIB nembak LONG di
        # pucuk tersembunyi 82-89; BCH A+ tembak pas RSI live 61). P12-LIVE + A+ staleness
        # = reinforcement rule lama di tick live; fade lemah = demote B (bos tetap ditanya).
        _rc=hr.fresh_recheck(cd, k_cache, rb, px=live_px(cd['sym']))
        if not _rc['ok']:
            done.discard(cd['key'])  # gak dikunci — kondisi live bisa berubah, sinyal boleh dinilai ulang
            st.setdefault('reject_cd',{})[cd['sym']+':'+cd['side']]=time.time()*1000+15*60*1000
            log({'event':'recheck_block','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade'],
                 'rsi_now':_rc['rsi_now'],'k_now':_rc['k_now'],'why':_rc['why']})
            continue
        if _rc['demote']:
            cd['grade']='B'
            log({'event':'recheck_demote','symbol':cd['sym'],'side':cd['side'],
                 'rsi_now':_rc['rsi_now'],'k_now':_rc['k_now'],'why':_rc['demote_why']})
        if n_open>=og.MAX_GLOBAL_POSITIONS:
            log({'event':'skip_full_position','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade']})
            done.discard(cd['key'])  # jangan dikunci done — kalau slot buka lagi, sinyal bisa dinilai ulang
            continue
        d=llm_call(cd['brief'])
        # v7.0: fence host MIN_CONF (P17) + echo rubric P21a DIHAPUS — keputusan = murni bos v7
        # (P8 internal <0.55 = REJECT; fence dobel justru bikin "penolak pasif" yang di protes user)
        # P9 NORMALISASI SIDE: kurir ngirim 'L'/'S', seluruh jalur mutasi pakai 'LONG'/'SHORT'.
        # 'L' != 'LONG' bikin SL/TP kebalik (bug BCH 21:51 WIB: LONG kena SL palsu di profit)
        _side=cd['side']
        cd['side']={'L':'LONG','S':'SHORT'}.get(_side,_side)
        _mtc=(cd.get('brief') or {}).get('metrics') or {}
        log({'event':'decision','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade'],
             'decision':d.get('decision'),'conf':d.get('confidence'),
             'rsi6rt':_mtc.get('rsi6Realtime'),'rsi_now':_rc.get('rsi_now'),'k_now':_rc.get('k_now'),
             'reason':d.get('reason'),'factor':d.get('key_factor')})
        # P39 FIX (ACC 30 Sep): reject_cd ditulis SEBELUM save_state — dulu ditulis
        # SETELAH save terakhir (535) & save berikutnya cuma terjadi saat CONFIRMED (695)
        # -> iterasi semua-REJECT gak pernah persist cooldown -> 303 panggilan jev
        # berulang <15m per 24 jam (LINK 55x, XAU 53x, TIA 31x, AAVE 14x).
        if d.get('decision')=='REJECT':
            st.setdefault('reject_cd',{})[cd['sym']+':'+_side]=time.time()*1000+15*60*1000
        if d.get('decision') not in ('CONFIRMED','REJECT'):
            # llm_err/gateway mati: JANGAN dedup permanen — lepas dari done supaya iterasi
            # berikutnya nanya lagi ke bos (bug UNI-A 20:40 WIB: grade A hilang selamanya)
            done.discard(cd.get('key'))
            st['done']=_p39_trim(done)
            log({'event':'retry_later','symbol':cd['sym'],'msg':'llm_err -> kandidat diulang iterasi berikut'})
        save_state(st)  # persist done-list + reject_cd (P39) lintas restart
        # P30 REJECT-COOLDOWN: REJECT = jangan tanya bos utk (sym,side) yg sama dlm 15 menit — hemat API jev
        # (kasus P29: ATOM SHORT ditanya 40x/2jam = 44% budget jev terbuang utk jawaban sama)
        if d.get('decision')!='CONFIRMED': continue
        # v7.1: Wick-flip P16-B DIMUSNAHKAN — keputusan arah bos mutlak (patch user:
        # flip mekanis di eksekutor = penyebab lose tersembunyi). Gak ada intervensi
        # arah lagi antara jawaban bos dan TradeExecutor.
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
        # CHOP SNIPER: regime masih dipakai maxhold + notif; SL/TP kini PURE ATR (v8.0)
        regime=cd.get('regime','RANGE')
        sl_pct=SL_PCT
        # P11: BOS YANG MIKIRIN SL/TP (varian eksekusi dari jev) — guard tetap ketat:
        variant=str(d.get('variant','')).upper() if isinstance(d,dict) else ''
        # === ERA BARU v8.0: PURE ATR ADAPTIVE SCALPER (directive user 1 Okt) ===
        # Multiplier statis (0.5x/0.67x/1.0x dari SL_PCT) DIHAPUS — SL/TP mengikuti
        # volatilitas riil koin via slSuggest (ATR14x1.5 MURNI tanpa clamp, v10.0; unit PERSEN
        # -> fraksi, unit-fix P36 tetap berlaku). Varian bos = modifikasi agresivitas ruang ATR.
        _ss={}
        try:
            _ss=(cd.get('brief') or {}).get('slSuggest') or {}
            _atr_f = float(_ss.get('sl_pct_suggest') or 1.2) / 100.0  # Konversi persen ke fraksi
        except Exception:
            _atr_f = 0.012  # Fallback 1.2% jika data kosong

        # Varian Bos Jev bertugas memodifikasi agresivitas ruang ATR secara adaptif:
        if variant == 'TIGHT':
            # v11.0 PRE-EMPTIVE: potong ruang ATR 50% (dulu 25%) — entri sudah di pucuk/
            # lembah absolut = koordinat harga terbaik, SL super tipis, rugi minimal.
            sl_pct = _atr_f * 0.50
            tp_rr = 2.5             # v11.0: RR 2.5 (dulu 2.0) — TP kilat linear
        elif variant == 'WIDE':
            sl_pct = _atr_f * 1.30  # Melebarkan ruang ATR sebesar 30% jika wick sedang mengamuk
            tp_rr = 2.5
        else:  # NORMAL atau Kosong
            sl_pct = _atr_f         # Ikut 100% volatilitas riil ATR koin bersangkutan (PAS DAN ADIL)
            tp_rr = 2.5             # Konsisten dengan target Scalp-Lock v7.3
        # v12.3.2 FIX FLOOR (directive user 2 Okt): floor SL = 1.5% — "SL 1.5%".
        # (v12.3.1 sempat salah set 0.7% — itu angka TRAIL lock, bukan SL; dikoreksi.)
        # Tetap ditagih SETELAH ×mult; WIDE/ATR besar tetap boleh > floor (max()).
        sl_pct = max(sl_pct, 0.015)
        try:
            if _ss.get('sl_pct_suggest'):
                _mult={'TIGHT':0.50,'WIDE':1.30}.get(variant,1.0)
                log({'event':'atr_sl','symbol':cd['sym'],'atr_suggest':float(_ss.get('sl_pct_suggest')),
                     'mult':_mult,'final_sl_pct':round(sl_pct*100,4),
                     'msg':f'SL = ATR14x1.5 x{_mult} (v8.0 PURE ATR) · v12.3.2 floor 1.5% post-mult'})
        except Exception: pass
        # (P32 ATR-SL lama DIGABUNG ke blok v8.0 di atas — ATR kini basis utama SL,
        # bukan widening-only; blok _sug_f>sl_pct DIHAPUS per directive v8.0.)
        # (P19 range-guard DIHAPUS v9.0 per directive — SL murni ATR linear, tanpa intervensi range.)
        # v9.0: P36 clamp statis DIHAPUS per directive — sl_pct murni 100% mengikuti
        # kalkulasi Pure ATR (slSuggest) secara linear tanpa pembatas atas/bawah.
        sl_d=entry*sl_pct; tp_d=sl_d*tp_rr  # SL % dari harga (proporsional semua coin)
        # v12.0 TP BAND SCALPER (directive user verbatim): TP dipaksa masuk band 0.6–1.5%
        # — kontrak harga CASH scalper, diterapkan SETELAH TP dihitung ATR (SL gak disentuh,
        # tetap ATR murni per kontrak "tanpa pembatasan" v10.0). Terdekat yang dulu kena = target.
        tp_pct=tp_d/entry if entry else 0.0
        if tp_pct<0.006: tp_d=entry*0.006
        elif tp_pct>0.015: tp_d=entry*0.015
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
                             'conf':d.get('confidence'),'reason':reason,
                             'engine':cd.get('src'),
                             'mf':(cd.get('brief') or {}).get('moneyFlow') or (cd.get('brief') or {}).get('tradfiMoneyFlow'),
                             'mss':(cd.get('brief') or {}).get('mss'),
                             'fvg':(cd.get('brief') or {}).get('fvgStatus'),
                             'entryLoc':(cd.get('brief') or {}).get('entryLoc')})+'\n🟢 <b>MODE LIVE</b> — order beneran terkirim')
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
             'conf':d.get('confidence'),'grade':cd['grade'],'reason':reason,
             'entryLoc':(cd.get('brief') or {}).get('entryLoc')})
        _br=cd.get('brief') or {}
        tg.send(tg.fmt_open({'symbol':cd['sym'],'side':side,'grade':cd['grade'],
                             'entry':entry,'sl':sl,'tp':tp,'tp_rr':tp_rr,
                             'qty':round((MARGIN*100*LEV)/entry,6),   # v7.1.1 #2: notional dinamis MARGIN*LEV (dulu hardcode 20.0)
                             'conf':d.get('confidence'),'reason':reason,
                             'variant':str(d.get('variant','')).upper(),
                             'engine':cd.get('src'),
                             'mf':_br.get('moneyFlow') or _br.get('tradfiMoneyFlow'),
                             'mss':_br.get('mss'),
                             'fvg':_br.get('fvgStatus'),
                             'regime':regime,'rsi6':_br.get('metrics',{}).get('rsi6Realtime'),
                             'entryLoc':_br.get('entryLoc'),
                             'godmode':_br.get('godmode'),
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
        tg.send(tg.fmt_briefing(rep, st.get('open',{}), sample, saldo=st.get('saldo',0.0)))
        # P18-fix: marker SETELAH kirim → notif berikutnya reset 0/0, briefing tetap 24 jam penuh
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'.dewa_briefing_mark'),'w').write(time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()))
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
