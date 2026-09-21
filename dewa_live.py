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

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)
import reversion_bot as rb
import dewa_skill as ds
import order_guard as og
import tg_notify as tg
import order_cleanup as oc

og.MAX_GLOBAL_POSITIONS=5

FEE=0.0005; LEV=10; MARGIN=0.02
BE_TRIG=0.0010; BE_OFF=0.0006; SL_MIN=0.0035; MAXHOLD=480
LIVE=False   # dry run default

LOG='/home/agentuser/dewa_live_log.jsonl'
STATE='/home/agentuser/dewa_live_state.json'

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
            f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1",timeout=10).read())
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
    body=json.dumps({"model":model,"temperature":0.1,"max_tokens":1500,
        "messages":[{"role":"system","content":ds.SYSTEM_PROMPT},
                    {"role":"user","content":json.dumps(brief)}]}).encode()
    req=urllib.request.Request(base.rstrip('/')+"/chat/completions",data=body,
        headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            msg=json.loads(r.read())["choices"][0]["message"]
        txt=msg.get("content") or msg.get("reasoning_content") or ""
        txt=txt[txt.find("{"):txt.rfind("}")+1]
        return json.loads(txt)
    except Exception as e:
        return {"decision":"REJECT","confidence":0,"reason":f"llm_err:{str(e)[:60]}"}

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
            if hit is None and bars_open>=MAXHOLD: hit='TIME'; exit_px=float(last[4])
            if hit:
                mv=(exit_px-p['entry'])/p['entry']*(1 if side=='LONG' else -1)
                fee=2*FEE if hit!='SL' else FEE+FEE  # SL full taker, lainnya maker-ish sim
                pnl=100*MARGIN*(mv*LEV-fee*LEV)
                realized.append({'sym':sym,'hit':hit,'pnl':round(pnl,2),'bars':round(bars_open,1),
                                 'conf':p.get('conf'),'grade':p.get('grade'),'side':side})
                log({'event':'exit','symbol':sym,'hit':hit,'pnl':pnl,'conf':p.get('conf')})
                st['saldo']=round(st.get('saldo',0)+pnl,2)
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
    """Ambil reasoning bos terakhir utk symbol dari log."""
    try:
        with open(LOG) as f:
            for line in reversed(f.readlines()[-200:]):
                e=json.loads(line)
                if e.get('event')=='decision' and e.get('symbol')==sym:
                    return e.get('reason','')
    except Exception: pass
    return ''

def iterate(once=False):
    st=load_state()
    k_cache={}
    # 1) kelola posisi terbuka dulu
    realized=manage_open(st,k_cache)
    # 2) kurir: cari kandidat baru di candle TERTUTUP terakhir
    n_open=len(st['open'])
    candidates=[]
    for sym in PAIRS:
        try:
            k5=vg.fetch_hist_klines(sym,'5m',600)
            k_cache[sym]=k5
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rb.rsi(c); zz=rb.zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            # sinyal di 3 bar terakhir (realtime; kurir dihitung sekali per iterasi)
            sigs=rb.gen_signals(kk,rs,zz,vsma)
            for (si,side,grade) in sigs[-3:] if sigs else []:
                i=si
                if i>=len(kk)-3:
                    if sym in st['open']: continue
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
                                       'brief':brief,'entry_next':float(kk[i+1][1]) if i+1<len(kk) else None})
        except Exception as e:
            log({'event':'err','symbol':sym,'msg':str(e)[:80]})
    # 3) bos putuskan (batch, urut grade A dulu)
    candidates.sort(key=lambda x:(x['grade']!='A', x['sym']))
    confirmed=0
    for cd in candidates:
        d=llm_call(cd['brief'])
        log({'event':'decision','symbol':cd['sym'],'side':cd['side'],'grade':cd['grade'],
             'decision':d.get('decision'),'conf':d.get('confidence'),
             'reason':d.get('reason'),'factor':d.get('key_factor')})
        if d.get('decision')!='CONFIRMED': continue
        if n_open+confirmed>=og.MAX_GLOBAL_POSITIONS:
            log({'event':'skip_full','symbol':cd['sym']}); continue
        if LIVE:
            # TODO eksekusi nyata via order_guard + Binance API (butuh API key user)
            log({'event':'LIVE_ORDER_NOT_IMPLEMENTED','symbol':cd['sym']})
            continue
        entry=cd['entry_next']
        if entry is None: continue
        side=cd['side']
        sl_d=max(SL_MIN,entry*0.004); tp_d=sl_d*3.0
        sl=entry-sl_d if side=='LONG' else entry+sl_d
        tp=entry+tp_d if side=='LONG' else entry-tp_d
        st['open'][cd['sym']]={'side':side,'entry':entry,'sl':sl,'tp':tp,'be_moved':False,
                               'open_ts':int(time.time()*1000),'conf':d.get('confidence'),
                               'grade':cd['grade']}
        confirmed+=1
        reason=d.get('reason','') or d.get('key_factor','')
        log({'event':'open','symbol':cd['sym'],'side':side,'entry':entry,'sl':sl,'tp':tp,
             'conf':d.get('confidence'),'grade':cd['grade'],'reason':reason})
        tg.send(tg.fmt_open({'symbol':cd['sym'],'side':side,'grade':cd['grade'],
                             'entry':entry,'sl':sl,'tp':tp,
                             'conf':d.get('confidence'),'reason':reason}))
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
    ap.add_argument('--live',action='store_true')
    a=ap.parse_args()
    if a.live: LIVE=True
    if a.report:
        print(json.dumps(report_daily(send_tg=True),indent=1))
    elif a.once:
        print(json.dumps(iterate(once=True),indent=1))
    else:
        print(f"[dewa-live] loop start pairs={len(PAIRS)} LIVE={LIVE}",flush=True)
        while True:
            try:
                r=iterate()
                print(datetime.now(timezone.utc).strftime('%H:%M'), r, flush=True)
            except Exception as e:
                print('ERR',repr(e),flush=True)
            time.sleep(60)
