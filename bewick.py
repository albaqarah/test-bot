#!/usr/bin/env python3
"""BE-system + anti-instant-SL filter: wick rejection wajib di candle sinyal.
LONG: wick bawah >= 40% range (rejection dump beneran)
SHORT: wick atas >= 40% range
Lalu ukur apakah full-SL turun drastis di semua 41 pair.
"""
import importlib.util, json, time, statistics
import os
spec=importlib.util.spec_from_file_location('vg',os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15_grade.py'))
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf',os.path.join(os.path.dirname(os.path.abspath(__file__)),'backtest_v15x_final.py'))
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)

FEE_M=0.0002; FEE_T=0.0005; LEV=3; MARGIN=0.10

PAIRS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
       'LINKUSDT','DOTUSDT','LTCUSDT','BCHUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
       'WLDUSDT','ORDIUSDT','ENAUSDT','WIFUSDT','ONDOUSDT','HYPEUSDT','JUPUSDT','RUNEUSDT',
       'AAVEUSDT','UNIUSDT','FETUSDT','GALAUSDT','CRVUSDT','LDOUSDT','ARBUSDT','OPUSDT',
       'ATOMUSDT','FILUSDT','INJUSDT','SEIUSDT','TRXUSDT','PAXGUSDT','XAUUSDT','XAGUSDT','XPTUSDT']

def run_be_wick(s,k,imb,cvd,wick_min=0.15,be_trig=0.001,be_off=0.0006,rr=3.0,maxhold=480,sl_min=0.003):
    kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k]
    t=[r[0] for r in kk]; o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]; v=[r[5] for r in kk]
    vsma=[None]*len(v)
    for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
    equity=100.0; total=0; wins=0; be_n=0; sl_n=0; pnl_tot=0.0; sig=0
    for i in range(30,len(c)-2):
        g,side=vg.grade(kk,i,imb,cvd,vsma)
        if not g or g not in ('A','B'): continue
        # ANTI-INSTANT-SL: rejection wick di bar SEBELUM sinyal (probe bar)
        o0,h0,l0,c0=o[i-1],h[i-1],l[i-1],c[i-1]
        rng0=h0-l0
        if rng0<=0: continue
        if side=='L':
            wl0=(min(o0,c0)-l0)/rng0
            if wl0 < 0.20: continue      # bar sebelumnya harus punya rejection dump
        else:
            wh0=(h0-max(o0,c0))/rng0
            if wh0 < 0.20: continue
        sig+=1
        entry=o[i+1]
        sl_d=max(sl_min, entry*0.004)
        tp_d=sl_d*rr
        sl=entry-sl_d if side=='L' else entry+sl_d
        tp=entry+tp_d if side=='L' else entry-tp_d
        be_moved=False; hit=None; exit_px=None
        for j in range(i+1,min(i+1+maxhold,len(c))):
            if side=='L':
                if l[j]<=sl: hit='BE' if be_moved else 'S'; exit_px=sl; break
                if h[j]>=tp: hit='T'; exit_px=tp; break
                if not be_moved and h[j]>=entry*(1+be_trig):
                    be_moved=True; sl=entry*(1+be_off)
            else:
                if h[j]>=sl: hit='BE' if be_moved else 'S'; exit_px=sl; break
                if l[j]<=tp: hit='T'; exit_px=tp; break
                if not be_moved and l[j]<=entry*(1-be_trig):
                    be_moved=True; sl=entry*(1-be_off)
        if hit is None: continue
        total+=1
        mv=(exit_px-entry)/entry*(1 if side=='L' else -1)
        if hit=='T': wins+=1; fee=FEE_M*2
        elif hit=='BE': be_n+=1; fee=FEE_M*2
        else: sl_n+=1; fee=FEE_M+FEE_T
        pnl=equity*MARGIN*(mv*LEV-fee*LEV)
        equity+=pnl; pnl_tot+=pnl
    return {"signals":sig,"trades":total,"TP":wins,"BE":be_n,"SL":sl_n,
            "non_loss":round(100*(wins+be_n)/total,1) if total else 0,
            "pnl_usd":round(pnl_tot,2),"equity_end":round(equity,2)}

if __name__=="__main__":
    print("BE-system + wick rejection 40% | 41 pair | IS (6000 bar terbaru)\n")
    results={}
    tot_pnl=0.0; pos=0; nl=[]
    for s in PAIRS:
        try:
            k=vg.fetch_hist_klines(s,'5m',6000)
            imb=vg.imbalance(k); cvd=btf.fetch_cvd(s)
            r=run_be_wick(s,k,imb,cvd)
            results[s]=r; tot_pnl+=r['pnl_usd']; pos+= 1 if r['pnl_usd']>0 else 0
            if r['trades']: nl.append(r['non_loss'])
            print(f"{s}: {json.dumps(r)}")
            time.sleep(0.3)
        except Exception as e:
            print(f"{s}: ERR {str(e)[:60]}")
    print(f"\n===== TOTAL =====")
    print(f"Pair profit: {pos}/{len(PAIRS)}")
    print(f"TOTAL PnL: {tot_pnl:+.2f} USD")
    print(f"Non-loss median: {statistics.median(nl) if nl else 0:.1f}%  max: {max(nl) if nl else 0}%")
    best=sorted(results.items(), key=lambda x:-x[1]['pnl_usd'])[:5]
    print("Top5:", [(k,v['pnl_usd']) for k,v in best])
    json.dump(results, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'bewick_results.json'),'w'), indent=1)
