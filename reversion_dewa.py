#!/usr/bin/env python3
"""
reversion_dewa.py — V2: regime-ADAPTIF, tidak ada yang dimatikan kaku.
Semua 41 pair, semua regime tetap trading:

TREND_UP   : LONG pullback (grade A/B) + SHORT counter hanya grade A sniper (climax ekstrem + volume)
TREND_DOWN : mirror-nya
RANGE/CHOP : sniper scalp dua arah — ambang lebih ketat (RSI<20 / >80, |z|>2, grade A wajib)
             TP lebih cepat (2R) karena chop mean-revert cepat, maxhold lebih pendek
Semua tetap: BE-system + wick climax + fee-aware. IS 4000 / OOS 2000 bar.
"""
import importlib.util, json, statistics

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)
import reversion_bot as rb   # reuse rsi, zscore, ema_series, regime_1h, consts

LEV=10; MARGIN=0.02
FEE_M=rb.FEE_M; FEE_T=rb.FEE_T

PAIRS=rb.PAIRS

def simulate_dewa(kk, sigs, regime, split):
    o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]
    res={}
    for seg in ('IS','OOS'):
        res[seg]={'trades':0,'TP':0,'BE':0,'SL':0,'pnl':0.0,'by_reg':{}}
    last_exit=0
    for (i,side,grade) in sigs:
        seg='IS' if i<split else 'OOS'
        if i<last_exit+2: continue
        # ---- regime ADAPTIF: tidak ada blok, hanya syarat kualitas beda ----
        tp_rr=3.0; maxhold=480
        if regime in ('TREND_UP','TREND_DOWN'):
            aligned = (side=='L') == (regime=='TREND_UP')
            if not aligned and grade!='A':
                continue  # counter-trend harus sniper grade A
        else:  # CHOP/RANGE: sniper scalp dua arah, ambang ketat via grade A saja
            if grade!='A':
                continue
            tp_rr=2.0; maxhold=240
        # ---- eksekusi (BE-system) ----
        entry=o[i+1]
        sl_d=max(rb.SL_MIN, entry*0.004)
        tp_d=sl_d*tp_rr
        sl=entry-sl_d if side=='L' else entry+sl_d
        tp=entry+tp_d if side=='L' else entry-tp_d
        be_moved=False; hit=None; exit_px=None; exit_fee=FEE_M
        j=i+1
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
        mv=(exit_px-entry)/entry*(1 if side=='L' else -1)
        pnl=100*MARGIN*(mv*LEV-exit_fee*LEV-FEE_M*LEV)
        r=res[seg]
        r['trades']+=1; r['pnl']+=pnl
        r['TP' if hit=='T' else 'BE' if hit=='BE' else 'SL']+=1
        key=f"{regime[:5]}"
        br=r['by_reg'].setdefault(key,{'trades':0,'pnl':0.0})
        br['trades']+=1; br['pnl']+=pnl
    for seg in res.values():
        n=seg['trades']
        seg['nonloss']=round(100*(seg['TP']+seg['BE'])/n,1) if n else 0
        seg['pnl']=round(seg['pnl'],2)
    return res

if __name__=='__main__':
    rows=[]; tot={'IS':0,'OOS':0}; pnl={'IS':0.0,'OOS':0.0}; pos={'IS':0,'OOS':0}
    regagg={}
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
            r=simulate_dewa(kk,sigs,reg,split)
            rows.append((s,reg,r))
            for seg in ('IS','OOS'):
                tot[seg]+=r[seg]['trades']; pnl[seg]+=r[seg]['pnl']
                pos[seg]+= 1 if r[seg]['pnl']>0 else 0
                for k2,brr in r[seg]['by_reg'].items():
                    ag=regagg.setdefault(seg,{}).setdefault(k2,{'trades':0,'pnl':0.0})
                    ag['trades']+=brr['trades']; ag['pnl']+=brr['pnl']
            print(f"{s:11s} reg={reg:10s} IS[tr={r['IS']['trades']:3d} nl={r['IS']['nonloss']:5.1f}% ${r['IS']['pnl']:6.2f}] "
                  f"OOS[tr={r['OOS']['trades']:3d} nl={r['OOS']['nonloss']:5.1f}% ${r['OOS']['pnl']:6.2f}]", flush=True)
        except Exception as e:
            print(s,'ERR',repr(e), flush=True)
    print("\n===== DEWA regime-adaptif | 41 pair SEMUA JALAN | margin $2 lev 10x =====")
    for seg in ('IS','OOS'):
        nl=[r[2][seg]['nonloss'] for r in rows if r[2][seg]['trades']]
        print(f"{seg}: trades={tot[seg]} pnl=${pnl[seg]:.2f} pair+={pos[seg]}/41 nl_med={statistics.median(nl):.1f}%")
        for k2,brr in sorted(regagg.get(seg,{}).items()):
            print(f"   regime {k2:6s}: trades={brr['trades']:4d} pnl=${brr['pnl']:6.2f}")
    json.dump({s:{'regime':reg,'IS':r['IS'],'OOS':r['OOS']} for s,reg,r in rows},
              open('/home/agentuser/dewa_results.json','w'), indent=1)
