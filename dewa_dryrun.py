#!/usr/bin/env python3
"""
dewa_dryrun.py — DRY RUN bot dewa: algoritma kurir setor kandidat A/B -> LLM bos putuskan.
REPLAY historis: kandidat diambil dari sinyal fade-ekstrem terakhir (6.000 bar), LLM beneran
dipanggil per kandidat (gateway lo), keputusan dicatat. EKSEKUSI DISIMULASI (dry run = ga ada
order beneran). Laporan: LLM terima berapa, terima berapa, kualitas keputusan.
"""
import importlib.util, json, os, time, statistics
from datetime import datetime, timezone

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)
import reversion_bot as rb
import dewa_skill as ds

FEE=0.0005; LEV=10; MARGIN=0.02; BE_TRIG=0.0010; BE_OFF=0.0006; SL_MIN=0.0035
MAX_POS=5

PAIRS=['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
       'BCHUSDT','LINKUSDT','DOTUSDT','LTCUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
       'WLDUSDT','ENAUSDT','JUPUSDT','ARBUSDT','OPUSDT','ATOMUSDT','CRVUSDT','LDOUSDT',
       'FETUSDT','GALAUSDT','INJUSDT','SEIUSDT','TRXUSDT','PAXGUSDT','XAUUSDT','XAGUSDT','XPTUSDT']

def llm_call(brief):
    base = os.environ.get("LLM_BASE_URL")
    key = os.environ.get("LLM_API_KEY") or os.environ.get("CUSTOM_API_KEY")
    model = os.environ.get("LLM_MODEL", "auto")
    if not base or not key:
        return None
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
        return {"decision":"ERROR","reason":str(e)[:80]}

def fund_last(sym):
    try:
        import urllib.request
        d=json.loads(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1",timeout=10).read())
        return float(d[0]['fundingRate'])
    except Exception: return 0.0

def simulate_trade(cd):
    """Eksekusi dry-run: BE-system + RR3 dari bar sinyal, max 480 bar."""
    kk=cd['kk']; i=cd['i']; side=cd['side']
    if i+2>=len(kk): return {'hit':'SKIP','pnl':0.0}
    entry=kk[i+1][1]
    sl_d=max(SL_MIN,entry*0.004); tp_d=sl_d*3.0
    sl=entry-sl_d if side=='L' else entry+sl_d
    tp=entry+tp_d if side=='L' else entry-tp_d
    be_moved=False; hit=None; exit_px=None; fee=FEE
    for j in range(i+1,min(i+481,len(kk))):
        o_,h_,l_,c_=kk[j][1],kk[j][2],kk[j][3],kk[j][4]
        if side=='L':
            if l_<=sl: hit='BE' if be_moved else 'S'; exit_px=sl; fee=FEE if be_moved else 0.0005; break
            if h_>=tp: hit='T'; exit_px=tp; break
            if not be_moved and h_>=entry*(1+BE_TRIG): be_moved=True; sl=entry*(1+BE_OFF)
        else:
            if h_<=sl: hit='BE' if be_moved else 'S'; exit_px=sl; fee=FEE if be_moved else 0.0005; break
            if l_>=tp: hit='T'; exit_px=tp; break
            if not be_moved and l_<=entry*(1-BE_TRIG): be_moved=True; sl=entry*(1-BE_OFF)
    if hit is None: return {'hit':'OPEN','pnl':0.0}
    mv=(exit_px-entry)/entry*(1 if side=='L' else -1)
    pnl=100*MARGIN*(mv*LEV-2*fee*LEV)
    return {'hit':hit,'pnl':round(pnl,2)}

if __name__=='__main__':
    # base url dari config hermes
    if not os.environ.get("LLM_BASE_URL"):
        try:
            line=[l for l in open(os.path.expanduser('~/.hermes/config.yaml')) if 'base_url' in l][0]
            os.environ["LLM_BASE_URL"]=line.split('base_url:')[1].strip().split()[0]
        except Exception: pass
    print("LLM base:", os.environ.get("LLM_BASE_URL","NONE"), flush=True)

    # 1) kumpulkan kandidat grade A/B dari 4 pair (dry run biar cepat & hemat LLM calls)
    cands=[]
    for s in PAIRS[:4]:
        try:
            k5=vg.fetch_hist_klines(s,'5m',6000)
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rb.rsi(c); zz=rb.zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            reg=rb.regime_1h(s)
            sigs=rb.gen_signals(kk,rs,zz,vsma)
            for (i,side,grade) in sigs[-6:]:   # 6 kandidat terakhir per pair (yang paling segar)
                o,h,l,cl=(kk[i][j] for j in (1,2,3,4))
                rng=h-l
                imb=((min(o,cl)-l)-(h-max(o,cl)))/rng if rng>0 else 0
                score={'imb':round(imb,3),'vol_x':round(kk[i][5]/vsma[i],2),'z':round(zz[i],2),'rsi':round(rs[i],1)}
                tv=None  # di dry run replay: TV snapshot live ga bisa direplay — dicatat None
                brief=ds.build_briefing(s,grade,side,score,reg,fund_last(s),tv,True)
                cands.append({'sym':s,'i':i,'side':side,'grade':grade,'brief':brief,'kk':kk})
            print(f"{s}: {len(sigs)} sinyal, kandidat di setor: {min(6,len(sigs))}", flush=True)
        except Exception as e:
            print(s,'ERR',repr(e), flush=True)

    print(f"\nTotal kandidat A/B disetor ke LLM: {len(cands)}", flush=True)
    # 2) bos putuskan + 3) simulasi eksekusi (dry run)
    results=[]; conf=0; rej=0; err=0
    for cd in cands:
        d=llm_call(cd['brief'])
        if d is None: print("LLM gagal dipanggil — stop"); break
        if d.get('decision')=='ERROR': err+=1; continue
        if d.get('decision')=='CONFIRMED':
            conf+=1; ok=simulate_trade(cd)
            results.append({'sym':cd['sym'],'side':cd['side'],'grade':cd['grade'],
                            'conf':d.get('confidence'),'factor':d.get('key_factor',''),
                            'reason':d.get('reason',''),'trade':ok})
            print(f"  CONFIRM {cd['sym']:9s} {cd['side']} g={cd['grade']} conf={d.get('confidence')} -> {ok['hit']} pnl=${ok['pnl']:.2f}", flush=True)
        else:
            rej+=1
            print(f"  REJECT  {cd['sym']:9s} {cd['side']} g={cd['grade']} -> {d.get('reason','')[:60]}", flush=True)
        time.sleep(0.5)
    print(f"\n===== DRY RUN RESULT =====")
    print(f"LLM terima: {conf} | reject: {rej} | error: {err}")
    if results:
        pnl=sum(r['trade']['pnl'] for r in results)
        tp=sum(1 for r in results if r['trade']['hit']=='T')
        be=sum(1 for r in results if r['trade']['hit']=='BE')
        sl=sum(1 for r in results if r['trade']['hit']=='S')
        print(f"Simulasi trade hasil keputusan bos: {len(results)} trades | TP={tp} BE={be} SL={sl} | PnL=${pnl:.2f}")
        for r in results: print(f"  {r['sym']:9s} {r['side']:5s} conf={r['conf']:>3} {r['factor'][:38]:38s} {r['trade']['hit']} ${r['trade']['pnl']:.2f}")
    json.dump({'accepted':results,'rejected':rej}, open('/home/agentuser/dryrun_results.json','w'), indent=1)
