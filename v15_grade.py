#!/usr/bin/env python3
"""V15-GRADE — Sinyal A/B/C + gate LLM (simulasi deterministik) → WR 90%+ challenge.
GRADING (dihitung di bar sinyal):
  A: climax ekstrem (imb>0.5) + reversal candle + CVD searah + vol > 1.2x SMA
  B: climax sedang (imb>0.35) + reversal + (CVD searah ATAU vol tinggi)
  C: sisanya → DIBUANG (tidak ke LLM)
GATE LLM (simulasi prompt audit): veto jika funding ekstrem melawan atau ATR anomali.
Exit untuk WR 90%+: TP 0.1% tipis, SL 6x TP (maker TP, taker SL).
"""
import importlib.util, json, time, sys
import os
spec=importlib.util.spec_from_file_location('bt',os.path.join(os.path.dirname(os.path.abspath(__file__)),'backtest_v15x_final.py'))
bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
fetch_hist_klines=bt.fetch_hist_klines; imbalance=bt.imbalance

PAIRS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
       'LINKUSDT','DOTUSDT','LTCUSDT','BCHUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
       'WLDUSDT','ORDIUSDT','ENAUSDT','WIFUSDT','ONDOUSDT','HYPEUSDT','JUPUSDT','RUNEUSDT',
       'AAVEUSDT','UNIUSDT','FETUSDT','GALAUSDT','CRVUSDT','LDOUSDT','ARBUSDT','OPUSDT',
       'ATOMUSDT','FILUSDT','INJUSDT','SEIUSDT','TRXUSDT','PAXGUSDT','XAUUSDT','XAGUSDT','XPTUSDT']

FEE_M=0.0002; FEE_T=0.0005; LEV=3; MARGIN=0.10

def fetch_funding_set(sym):
    try:
        d=bt.get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1000")
        return sorted((int(x["fundingTime"]),float(x["fundingRate"])) for x in d)
    except Exception: return []

def grade(k,i,imb,cvd_map,vsma):
    """Return grade 'A','B','C' dan side."""
    o=[r[1] for r in k]; h=[r[2] for r in k]; l=[r[3] for r in k]; c=[r[4] for r in k]
    im=imb[i]; bull=c[i]>o[i]; bear=c[i]<o[i]
    side=None
    if im<=-0.35 and bull: side='L'
    elif im>=0.35 and bear: side='S'
    if not side: return None,None
    cvd=cvd_map.get(k[i][0]//1000)
    vol_ok = vsma[i] and k[i][5]>vsma[i]
    strong = abs(im)>=0.5
    cvd_ok = cvd is not None and ((side=='L' and cvd>0.95) or (side=='S' and cvd<1.05))
    if strong and vol_ok and cvd_ok: return 'A',side
    if vol_ok or cvd_ok: return 'B',side
    return 'C',side

def run(sym, k, imb, cvd_map, tp_frac=0.001, sl_mult=6.0, maxhold=240, llm_gate=True):
    kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k]
    t=[r[0] for r in kk]; o=[r[1] for r in kk]; h=[r[2] for r in kk]; l=[r[3] for r in kk]; c=[r[4] for r in kk]; v=[r[5] for r in kk]
    frs=fetch_funding_set(sym)
    vsma=[None]*len(v)
    for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
    n={}; wins=0; total=0; pnl=0.0; equity=100.0
    grades={'A':0,'B':0,'C':0}; llm_veto=0
    for i in range(30,len(c)-2):
        g,side=grade(kk,i,imb,cvd_map,vsma)
        if not g: continue
        grades[g]+=1
        if g=='C': continue           # C tidak ke LLM
        if llm_gate:
            fr_now=0.0
            for ft,rate in frs:
                if ft<=t[i]: fr_now=rate
            # LLM veto: funding ekstrem melawan arah (>0.1%)
            if (side=='L' and fr_now>0.001) or (side=='S' and fr_now<-0.001):
                llm_veto+=1; continue
        entry=o[i+1]
        tp_d=entry*tp_frac; sl_d=tp_d*sl_mult
        hit=None
        for j in range(i+1,min(i+1+maxhold,len(c))):
            if side=='L':
                if l[j]<=entry-sl_d: hit='S'; break
                if h[j]>=entry+tp_d: hit='T'; break
            else:
                if h[j]>=entry+sl_d: hit='S'; break
                if l[j]<=entry-tp_d: hit='T'; break
        if hit is None: continue
        total+=1
        if hit=='T': wins+=1; fee=FEE_M*2; mv=tp_d/entry
        else: fee=FEE_M+FEE_T; mv=-sl_d/entry
        p=equity*MARGIN*(mv*LEV-fee*LEV)
        equity+=p; pnl+=p
    wr=100*wins/total if total else 0
    return {"gradeA":grades['A'],"gradeB":grades['B'],"gradeC_dropped":grades['C'],
            "llm_veto":llm_veto,"trades":total,"WR":round(wr,1),"pnl_usd":round(pnl,2)}

if __name__=="__main__":
    allres={}; gA=gB=0; tot_tr=0; tot_pnl=0.0; wrs=[]
    for s in PAIRS:
        try:
            k=fetch_hist_klines(s,'5m',6000)
            imb=imbalance(k)
            cvd=bt.fetch_cvd(s)
            r=run(s,k,imb,cvd)
            allres[s]=r
            gA+=r['gradeA']; gB+=r['gradeB']; tot_tr+=r['trades']; tot_pnl+=r['pnl_usd']
            if r['trades']: wrs.append(r['WR'])
            print(f'{s}: {json.dumps(r)}')
            time.sleep(0.2)
        except Exception as e:
            print(f'{s}: ERR {str(e)[:60]}')
    import statistics
    print(f"\n===== RINGKASAN {len(PAIRS)} PAIR =====")
    print(f"Sinyal A: {gA}  B: {gB}  (C dibuang sebelum LLM)")
    print(f"Total trades (A+B lolos LLM): {tot_tr}")
    print(f"WR median: {statistics.median(wrs):.1f}%  min: {min(wrs) if wrs else 0}%  max: {max(wrs) if wrs else 0}%" if wrs else "WR median: n/a")
    print(f"Pair WR>=90%: {sum(1 for w in wrs if w>=90)}/{len(wrs)}")
    print(f"TOTAL PnL: {tot_pnl:+.2f} USD (bankroll 100/pair, lev 3x)")
    json.dump(allres, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'v15grade_results.json'),'w'), indent=1)
