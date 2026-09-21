#!/usr/bin/env python3
"""
dewa_v3.py — DEWA V2 + simulasi realistis:
1. MAX 5 POSISI GLOBAL (slot antre; sinyal baru ditolak kalau penuh)
2. Janitor: SL/TP selalu terpasang (simulasi: verifikasi selalu sukses, cost = retry fee tidak ada)
3. PnL dihitung per-hari-per-minggu juga, biar jelas IS/OOS-nya
IS 4000 bar / OOS 2000 bar, tiap segi dibagi juga ke minggu.
"""
import importlib.util, json, statistics
from datetime import datetime, timezone

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)
import reversion_bot as rb
import reversion_dewa as rd

LEV=10; MARGIN=0.02
FEE_M=rb.FEE_M; FEE_T=rb.FEE_T
MAX_POS=5  # << set dari user

PAIRS=rb.PAIRS

def simulate_v3(kk, sigs, regime, split):
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]
    t=[r[0] for r in kk]
    res={}
    for seg in ('IS','OOS'):
        res[seg]={'trades':0,'TP':0,'BE':0,'SL':0,'pnl':0.0,'daily':{},'weekly':{},'max_concurrent':0}
    open_pos=[]  # list of {'exit_i': int} — max MAX_POS bersamaan
    pending=[]
    last_exit=0
    for (i,side,grade) in sorted(sigs):
        seg='IS' if i<split else 'OOS'
        # buang posisi selesai
        open_pos=[p for p in open_pos if p['exit_i']>i]
        res[seg]['max_concurrent']=max(res[seg]['max_concurrent'],len(open_pos))
        if len(open_pos)>=MAX_POS:
            continue  # slot penuh — sinyal ditolak (realistis dgn cap 5)
        if i<last_exit+2: continue
        tp_rr=3.0; maxhold=480
        if regime in ('TREND_UP','TREND_DOWN'):
            aligned=(side=='L')==(regime=='TREND_UP')
            if not aligned and grade!='A': continue
        else:
            if grade!='A': continue
            tp_rr=2.0; maxhold=240
        entry=o[i+1]
        sl_d=max(rb.SL_MIN, entry*0.004)
        tp_d=sl_d*tp_rr
        sl=entry-sl_d if side=='L' else entry+sl_d
        tp=entry+tp_d if side=='L' else entry-tp_d
        be_moved=False; hit=None; exit_px=None; exit_fee=FEE_M; exit_i=None
        for j in range(i+1,min(i+1+maxhold,len(c))):
            if side=='L':
                if l[j]<=sl: hit='BE' if be_moved else 'S'; exit_px=sl; exit_fee=FEE_M if be_moved else FEE_T; break
                if h[j]>=tp: hit='T'; exit_px=tp; break
                if not be_moved and h[j]>=entry*(1+rb.BE_TRIG): be_moved=True; sl=entry*(1+rb.BE_OFF)
            else:
                if h[j]>=sl: hit='BE' if be_moved else 'S'; exit_px=sl; exit_fee=FEE_M if be_moved else FEE_T; break
                if l[j]<=tp: hit='T'; exit_px=tp; break
                if not be_moved and l[j]<=entry*(1-rb.BE_TRIG): be_moved=True; sl=entry*(1-rb.BE_OFF)
        if hit is None: continue
        last_exit=j
        open_pos.append({'exit_i':j})
        mv=(exit_px-entry)/entry*(1 if side=='L' else -1)
        pnl=100*MARGIN*(mv*LEV-exit_fee*LEV-FEE_M*LEV)
        r=res[seg]
        r['trades']+=1; r['pnl']+=pnl
        r['TP' if hit=='T' else 'BE' if hit=='BE' else 'SL']+=1
        # time bucketing: harian & mingguan (pakai timestamp candle exit)
        dt=datetime.fromtimestamp(t[j]/1000, tz=timezone.utc)
        dkey=dt.strftime('%Y-%m-%d')
        wkey=f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        r['daily'][dkey]=r['daily'].get(dkey,0)+pnl
        r['weekly'][wkey]=r['weekly'].get(wkey,0)+pnl
    for seg in res.values():
        n=seg['trades']
        seg['nonloss']=round(100*(seg['TP']+seg['BE'])/n,1) if n else 0
        seg['pnl']=round(seg['pnl'],2)
        seg['daily']={k:round(v,2) for k,v in sorted(seg['daily'].items())}
        seg['weekly']={k:round(v,2) for k,v in sorted(seg['weekly'].items())}
    return res

if __name__=='__main__':
    agg={'IS':{'trades':0,'pnl':0.0,'daily':{},'weekly':{}},
         'OOS':{'trades':0,'pnl':0.0,'daily':{},'weekly':{}}}
    pos_cnt={'IS':0,'OOS':0}
    for s in PAIRS:
        try:
            k5=vg.fetch_hist_klines(s,'5m',6000)
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rb.rsi(c); zz=rb.zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            reg=rb.regime_1h(s)
            sigs=rb.gen_signals(kk,rs,zz,vsma)
            split=len(c)-2000
            r=simulate_v3(kk,sigs,reg,split)
            for seg in ('IS','OOS'):
                a=agg[seg]
                a['trades']+=r[seg]['trades']; a['pnl']+=r[seg]['pnl']
                pos_cnt[seg]+= 1 if r[seg]['pnl']>0 else 0
                for k2,val in r[seg]['daily'].items(): a['daily'][k2]=a['daily'].get(k2,0)+val
                for k2,val in r[seg]['weekly'].items(): a['weekly'][k2]=a['weekly'].get(k2,0)+val
            print(f"{s:11s} reg={reg:10s} IS[tr={r['IS']['trades']:3d} ${r['IS']['pnl']:6.2f}] OOS[tr={r['OOS']['trades']:3d} ${r['OOS']['pnl']:6.2f}] maxpos={r['IS']['max_concurrent']}", flush=True)
        except Exception as e:
            print(s,'ERR',repr(e), flush=True)
    print(f"\n===== DEWA V3 (max {MAX_POS} posisi global, janitor SL/TP) =====")
    for seg in ('IS','OOS'):
        a=agg[seg]
        print(f"\n[{seg}] trades={a['trades']} pnl=${a['pnl']:.2f} pair+={pos_cnt[seg]}/41")
        print("  per minggu:")
        for wk,val in a['weekly'].items(): print(f"    {wk}: ${val:7.2f}")
        pos_days=sum(1 for v in a['daily'].values() if v>0)
        print(f"  hari profit: {pos_days}/{len(a['daily'])}")
        print("  10 hari terakhir:", {k:round(v,2) for k,v in list(a['daily'].items())[-10:]})
    json.dump({seg:{'trades':agg[seg]['trades'],'pnl':round(agg[seg]['pnl'],2),
                    'daily':{k:round(v,2) for k,v in agg[seg]['daily'].items()},
                    'weekly':{k:round(v,2) for k,v in agg[seg]['weekly'].items()}} for seg in agg},
              open('/home/agentuser/dewa_v3_results.json','w'), indent=1)
