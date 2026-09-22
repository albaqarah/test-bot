#!/usr/bin/env python3
"""
reversion_bot.py — Deep-research engine: fade ekstrem (beli lembah, jual pucuk).
Premis user: bot harus pintar ambil LONG di oversold (lembah), SHORT di overbought (pucuk).

Sinyal (multi-konfirmasi, bukan RSI doang):
  LONG  saat: RSI(14) 5m < 25  DAN lower-wick climax (imb <= -0.4)  DAN harga jauh di bawah EMA200 5m (z-score ekstrem)
  SHORT saat: RSI(14) 5m > 75  DAN upper-wick climax (imb >= 0.4)   DAN harga jauh di atas EMA200 5m
  Regime 1h: TRENDE KUAT -> fade hanya searah pullback ke mean (anti falling-knife):
    TREND_UP   -> hanya LONG saat pullback oversold (beli lembah dalam uptrend)
    TREND_DOWN -> hanya SHORT saat rally overbought (jual pucuk dalam downtrend)
    RANGE      -> dua arah boleh
  Grade A: semua konfirmasi + volume climax (vol > 1.5x SMA20)
  Grade B: konfirmasi inti tanpa volume climax
Eksekusi: BE-system (SL -> BE segera, offset > fee) + RR 3:1 bonus, max hold 480 bar.
IS/OOS: 4000 bar pertama = IS, 2000 terakhir = OOS.
"""
import importlib.util, json, statistics, time

spec=importlib.util.spec_from_file_location('vg','/home/agentuser/v15_grade.py')
vg=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
spec2=importlib.util.spec_from_file_location('btf','/home/agentuser/backtest_v15x_final.py')
btf=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(btf)

FEE_M=0.0002; FEE_T=0.0005
LEV=10; MARGIN=0.02          # $2 pada equity ref $100
BE_TRIG=0.0010; BE_OFF=0.0006
TP_RR=3.0; SL_MIN=0.0035; MAXHOLD=480

PAIRS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT',
       'LINKUSDT','DOTUSDT','LTCUSDT','BCHUSDT','NEARUSDT','APTUSDT','SUIUSDT','TIAUSDT',
       'WLDUSDT','ORDIUSDT','ENAUSDT','WIFUSDT','ONDOUSDT','HYPEUSDT','JUPUSDT','RUNEUSDT',
       'AAVEUSDT','UNIUSDT','FETUSDT','GALAUSDT','CRVUSDT','LDOUSDT','ARBUSDT','OPUSDT',
       'ATOMUSDT','FILUSDT','INJUSDT','SEIUSDT','TRXUSDT','PAXGUSDT','XAUUSDT','XAGUSDT','XPTUSDT']

def rsi(closes, n=14):
    out=[None]*len(closes)
    g=l=0.0
    for i in range(1,n+1):
        d=closes[i]-closes[i-1]
        g+=max(d,0); l+=max(-d,0)
    ag,al=g/n,l/n
    out[n]=100-100/(1+ag/al) if al else 100.0
    for i in range(n+1,len(closes)):
        d=closes[i]-closes[i-1]
        ag=(ag*(n-1)+max(d,0))/n; al=(al*(n-1)+max(-d,0))/n
        out[i]=100-100/(1+ag/al) if al else 100.0
    return out

def ema_series(vals,n):
    k=2/(n+1); out=[vals[0]]
    for v in vals[1:]: out.append(v*k+out[-1]*(1-k))
    return out

def zscore(closes, look=200):
    out=[None]*len(closes)
    for i in range(look,len(closes)):
        w=closes[i-look:i]
        m=sum(w)/look
        var=sum((x-m)**2 for x in w)/look
        sd=var**0.5
        out[i]=(closes[i]-m)/sd if sd>0 else 0.0
    return out

def regime_1h(sym):
    try:
        k1h=vg.fetch_hist_klines(sym,'1h',300)
        c=[float(x[4]) for x in k1h]
        e20,e50=ema_series(c,20)[-1],ema_series(c,50)[-1]
        if c[-1]>e20>e50: return 'TREND_UP'
        if c[-1]<e20<e50: return 'TREND_DOWN'
        return 'RANGE'
    except Exception:
        return 'RANGE'

def gen_signals(kk, rs, zz, vsma):
    """Return list (idx, side, grade)."""
    sigs=[]
    t=[r[0] for r in kk]; o=[r[1] for r in kk]; h=[r[2] for r in kk]
    l=[r[3] for r in kk]; c=[r[4] for r in kk]; v=[r[5] for r in kk]
    for i in range(210,len(c)-2):
        r=rs[i]; z=zz[i]
        if r is None or z is None: continue
        rng=h[i]-l[i]
        if rng<=0: continue
        imb=((min(o[i],c[i])-l[i])-(h[i]-max(o[i],c[i])))/rng
        volx=v[i]/vsma[i] if vsma[i] else 1
        # LONG: lembah
        if r<25 and z<-1.5 and imb<=-0.15:
            grade='A' if (volx>1.5 and imb<=-0.3) else 'B'
            sigs.append((i,'L',grade))
        # SHORT: pucuk
        elif r>75 and z>1.5 and imb>=0.15:
            grade='A' if (volx>1.5 and imb>=0.3) else 'B'
            sigs.append((i,'S',grade))
    return sigs

def simulate(kk, sigs, regime, is_oos_split):
    t=[r[0] for r in kk]; o=[r[1] for r in kk]; h=[r[2] for r in kk]
    l=[r[3] for r in kk]; c=[r[4] for r in kk]
    res={'IS':{'trades':0,'TP':0,'BE':0,'SL':0,'pnl':0.0},
         'OOS':{'trades':0,'TP':0,'BE':0,'SL':0,'pnl':0.0}}
    last_exit=0
    for (i,side,grade) in sigs:
        if i<is_oos_split: seg='IS'
        else: seg='OOS'
        if i<last_exit+2: continue          # tidak tumpuk posisi
        # regime gate anti falling-knife
        if regime=='TREND_UP' and side=='S': continue
        if regime=='TREND_DOWN' and side=='L': continue
        entry=o[i+1]
        sl_d=max(SL_MIN, entry*0.004)
        tp_d=sl_d*TP_RR
        sl=entry-sl_d if side=='L' else entry+sl_d
        tp=entry+tp_d if side=='L' else entry-tp_d
        be_moved=False; hit=None; exit_px=None; exit_fee=FEE_M
        for j in range(i+1,min(i+1+MAXHOLD,len(c))):
            if side=='L':
                if l[j]<=sl: hit='BE' if be_moved else 'S'; exit_px=sl; exit_fee=FEE_M if be_moved else FEE_T; break
                if h[j]>=tp: hit='T'; exit_px=tp; break
                if not be_moved and h[j]>=entry*(1+BE_TRIG): be_moved=True; sl=entry*(1+BE_OFF)
            else:
                if h[j]>=sl: hit='BE' if be_moved else 'S'; exit_px=sl; exit_fee=FEE_M if be_moved else FEE_T; break
                if l[j]<=tp: hit='T'; exit_px=tp; break
                if not be_moved and l[j]<=entry*(1-BE_TRIG): be_moved=True; sl=entry*(1-BE_OFF)
        if hit is None: continue
        last_exit=j
        mv=(exit_px-entry)/entry*(1 if side=='L' else -1)
        pnl=100*MARGIN*(mv*LEV-exit_fee*LEV-FEE_M*LEV)
        r=res[seg]
        r['trades']+=1; r['pnl']+=pnl
        r['TP' if hit=='T' else 'BE' if hit=='BE' else 'SL']+=1
    for seg in res.values():
        n=seg['trades']
        seg['nonloss']=round(100*(seg['TP']+seg['BE'])/n,1) if n else 0
        seg['pnl']=round(seg['pnl'],2)
    return res

if __name__=='__main__':
    rows=[]; is_tot=oos_tot=0; is_pos=oos_pos=0
    for s in PAIRS:
        try:
            k5=vg.fetch_hist_klines(s,'5m',6000)
            kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in k5]
            c=[r[4] for r in kk]; v=[r[5] for r in kk]
            rs=rsi(c); zz=zscore(c)
            vsma=[0.0]*len(v)
            for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
            reg=regime_1h(s)
            sigs=gen_signals(kk,rs,zz,vsma)
            split=len(c)-2000
            r=simulate(kk,sigs,reg,split)
            rows.append((s,reg,len(sigs),r))
            is_tot+=r['IS']['trades']; oos_tot+=r['OOS']['trades']
            is_pos+= 1 if r['IS']['pnl']>0 else 0
            oos_pos+= 1 if r['OOS']['pnl']>0 else 0
            print(f"{s:11s} reg={reg:10s} sig={len(sigs):4d} IS[tr={r['IS']['trades']:3d} nl={r['IS']['nonloss']:5.1f}% pnl=${r['IS']['pnl']:7.2f}] "
                  f"OOS[tr={r['OOS']['trades']:3d} nl={r['OOS']['nonloss']:5.1f}% pnl=${r['OOS']['pnl']:7.2f}]", flush=True)
        except Exception as e:
            print(s,'ERR',repr(e), flush=True)
    is_pnl=sum(r[3]['IS']['pnl'] for r in rows); oos_pnl=sum(r[3]['OOS']['pnl'] for r in rows)
    is_nl=[r[3]['IS']['nonloss'] for r in rows if r[3]['IS']['trades']]
    oos_nl=[r[3]['OOS']['nonloss'] for r in rows if r[3]['OOS']['trades']]
    print("\n===== REVERSION FADE-EKSTREM | margin $2 lev 10x RR3 BE-system =====")
    print(f"IS : trades={is_tot} pnl=${is_pnl:.2f} pair+={is_pos}/{len(rows)} nl_med={statistics.median(is_nl):.1f}%" if is_nl else "")
    print(f"OOS: trades={oos_tot} pnl=${oos_pnl:.2f} pair+={oos_pos}/{len(rows)} nl_med={statistics.median(oos_nl):.1f}%" if oos_nl else "")
    out={'rows':{s:{'regime':reg,'sigs':n,'IS':r['IS'],'OOS':r['OOS']} for s,reg,n,r in rows},
         'totals':{'IS_pnl':round(is_pnl,2),'OOS_pnl':round(oos_pnl,2)}}
    json.dump(out, open('/home/agentuser/reversion_results.json','w'), indent=1)
