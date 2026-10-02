#!/usr/bin/env python3
"""test_v7.py — regresi TYPESAFE SNIPER v7.0 (rombak total 30 Sep 2026).
Coverage: HTF filter (anti-trap + fail-closed), align_htf forward-fill,
3 engine preset (threshold persis spec user), type-guard bos v7,
payload kontrak JSON, dan static check kode-mati (anti numpuk bug)."""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversion_bot as rb
import hybrid_rules as hr
import dewa_skill as ds
import jev_bridge as jb
import smc_engine as smc

PASS=0; FAIL=0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond: PASS+=1; print(f"  ok  {name}")
    else: FAIL+=1; print(f" FAIL {name} {detail}")

def mk_kk(spec):
    """spec: list bar [ts,o,h,l,c,v] -> kk format pipeline."""
    return [[int(s[0]),float(s[1]),float(s[2]),float(s[3]),float(s[4]),float(s[5])] for s in spec]

def base_kk(n=300, px=100.0):
    return [[i*300000, px, px*1.001, px*0.999, px, 10.0] for i in range(n)]

# ---------- 1. align_htf forward-fill ----------
m={1000:(1.0,2.0),1500:(3.0,4.0)}
al=hr.align_htf([500,1000,1200,1500,1700], m)
check('align_htf ffill', al==[None,(1.0,2.0),(1.0,2.0),(3.0,4.0),(3.0,4.0)], str(al))
check('align_htf kosong', hr.align_htf([1,2],{})==[None,None])

# ---------- 2. FADE CLIMAX threshold persis spec ----------
# LONG: RSI6<20, z<-1.5, wick bawah>=40%  (o=99,c=92,h=99.5,l=87 -> wick=(92-87)/12.5=40%)
kk=base_kk(300)
for i in range(100,297): kk[i][4]=100+(0.5 if i%2 else -0.5)  # history berosilasi (z nyata)
kk[297]=[297*300000, 99.0, 99.5, 87.0, 92.0, 60.0]
c=[r[4] for r in kk]; v=[r[5] for r in kk]
rs=rb.rsi6(c); zz=rb.zscore(c)
vsma=[0.0]*len(v)
for i in range(20,len(v)): vsma[i]=sum(v[i-20:i])/20
fade=hr.gen_fade_climax(kk,rs,zz,vsma)
check('fade LONG RSI6<20 z<-1.5 wick>=40%', any(s[1]=='L' for s in fade), str(fade))
# drop sedang (RSI di band tengah, wick sah): TIDAK boleh nembak fade
kk2=base_kk(300)
for i in range(100,297): kk2[i][4]=100+(0.5 if i%2 else -0.5)
kk2[297]=[297*300000, 99.0, 99.5, 93.0, 96.0, 60.0]
c2=[r[4] for r in kk2]
rs2=rb.rsi6(c2); zz2=rb.zscore(c2)
check('fade drop sedang (RSI/z kurang ekstrem) ditolak', not any(s[1]=='L' for s in hr.gen_fade_climax(kk2,rs2,zz2,vsma)),
      str(hr.gen_fade_climax(kk2,rs2,zz2,vsma)))
# wick cuma ~27%: TIDAK boleh (o=90,c=95,l=88,h=95.5 -> wick=(90-88)/7.5=27%)
kk3=base_kk(300)
for i in range(100,297): kk3[i][4]=100+(0.5 if i%2 else -0.5)
kk3[297]=[297*300000, 90.0, 95.5, 88.0, 95.0, 60.0]
c3=[r[4] for r in kk3]
rs3=rb.rsi6(c3); zz3=rb.zscore(c3)
check('fade wick 27% ditolak (<40%)', not any(s[1]=='L' for s in hr.gen_fade_climax(kk3,rs3,zz3,vsma)),
      str(hr.gen_fade_climax(kk3,rs3,zz3,vsma)))

# ---------- 3. SCALP HIGH-MOMENTUM ----------
def scalp_case(o,h,l,cx,vx,reds=0):
    """Breakout bar di ujung; reds = jumlah bar merah sebelum breakout (jaga RSI6 <=85)."""
    k=base_kk(300)
    for j in range(reds):
        k[-4-j]=[ (297-1-j)*300000, 100.5, 100.8, 99.8, 99.0, 10.0]
    k[-3]=[297*300000,o,h,l,cx,vx]
    cc=[r[4] for r in k]
    rr=rb.rsi6(cc); z=rb.zscore(cc)
    vv=[r[5] for r in k]
    vm=[0.0]*len(vv)
    for i in range(20,len(vv)): vm[i]=sum(vv[i-20:i])/20
    return hr.gen_scalp_momentum(k,rr,vm)
check('scalp v7.1: volx>=1.2 LONG (volx besar + body besar tetap masuk)', any(s[1]=='L' for s in scalp_case(99.5,102.5,99.4,102.3,25.0,reds=2)))
# v9.0: gate volx = 1.2 normal, 1.0 saat RSI6 lembah(<25)/pucuk(>75) — isolasi penuh (RSI sintetis)
def scalp_case_rs(rsx, vol_abs):
    k=base_kk(300)
    k[297]=[297*300000, 99.5, 102.5, 99.4, 102.3, vol_abs]
    rr=[50.0]*300; rr[297]=rsx
    vv=[r[5] for r in k]; vm=[0.0]*len(vv)
    for i in range(20,len(vv)): vm[i]=sum(vv[i-20:i])/20
    return hr.gen_scalp_momentum(k,rr,vm)
check('v9.0 scalp: RSI6 netral (50) + volx 1.09 ditolak (gate normal 1.2)', not scalp_case_rs(50.0,11.5))
check('v9.0 scalp: RSI6 netral (50) + volx 2.22 lolos gate normal', any(s[1]=='L' for s in scalp_case_rs(50.0,25.0)))
check('v9.0 scalp relief: RSI6 pucuk (80) + volx 1.09 lolos (gate 1.0)', any(s[1]=='L' for s in scalp_case_rs(80.0,11.5)))
check('scalp v7.1: body kecil (33%) TETAP lolos — kualitas body dinilai bos', any(s[1]=='L' for s in scalp_case(99.5,103.0,98.5,101.0,25.0,reds=2)),
      str(scalp_case(99.5,103.0,98.5,101.0,25.0,reds=2)))
check('scalp grade: volx 1.4=B, volx>=2.0=A',
      (scalp_case(99.5,102.5,99.4,102.3,14.0,reds=2) or [(0,0,'X')])[0][2]=='B' and
      (scalp_case(99.5,102.5,99.4,102.3,25.0,reds=2) or [(0,0,'X')])[0][2]=='A')
# P12 guard: LONG di RSI6>85 diblokir -> bikin bar naik terus sblm breakout
k=base_kk(300)
for i in range(280,300): k[i]=[i*300000, 100+i-280, 100.6+i-280, 99.9, 100.5+i-280, 10.0]  # naik terus
k[-3]=[297*300000, 120.0, 124.0, 119.8, 123.6, 40.0]
cc=[r[4] for r in k]; rr=rb.rsi6(cc)
vv=[r[5] for r in k]; vm=[0.0]*len(vv)
for i in range(20,len(vv)): vm[i]=sum(vv[i-20:i])/20
check('scalp P12: RSI6 ekstrem naik -> LONG diblokir', not any(s[1]=='L' for s in hr.gen_scalp_momentum(k,rr,vm)),
      f"rsi6={rr[-3]:.1f}")

# ---------- 4. HTF FILTER (Anti-Trap) ----------
def htf_case(src, e20, e50, struct='RANGING'):
    """Kandidat 1 bar di ujung; src fade=climax lembah, scalp=breakout naik."""
    k=base_kk(300)
    if src=='fade':
        for j in range(100,297): k[j][4]=100+(0.5 if j%2 else -0.5)
        k[297]=[297*300000, 99.0, 99.5, 87.0, 92.0, 60.0]
    else:
        for j in range(2):
            k[296-j]=[(296-j)*300000, 100.5, 100.8, 99.8, 99.0, 10.0]
        k[297]=[297*300000, 99.5, 102.5, 99.4, 102.3, 25.0]
    cc=[r[4] for r in k]; rr=rb.rsi6(cc); z=rb.zscore(cc)
    vv=[r[5] for r in k]; vm=[0.0]*len(vv)
    for i in range(20,len(vv)): vm[i]=sum(vv[i-20:i])/20
    htf=[(e20,e50)]*len(k)
    return hr.gen_hybrid(k,rr,z,vm,htf,struct)
# v8.0: EMA-cross 15m DICABUT dari gerbang kurir — cross berlawanan GAK lagi blok (bos menilai arah via JSON)
check('v8.0 HTF: EMA-cross 15m dicabut — scalp lolos walau cross berlawanan', any(s[1]=='L' and s[3]=='scalp' for s in htf_case('scalp',10.0,11.0)), str(htf_case('scalp',10.0,11.0)))
check('v8.0 HTF: 1h BEARISH_EXTREME tetap blok LONG non-fade', not htf_case('scalp',12.0,11.0,'BEARISH_EXTREME_DUMP'))
# v9.0: fade TIDAK dikecualikan lagi — veto 1h ekstrem berlaku semua engine
check('v9.0 HTF: fade LONG ikut veto 1h BEARISH_EXTREME (gak dikecualikan lagi)', not any(s[1]=='L' and s[3]=='fade' for s in htf_case('fade',10.0,11.0,'BEARISH_EXTREME_DUMP')),
      str(htf_case('fade',10.0,11.0,'BEARISH_EXTREME_DUMP')))
check('v9.0 HTF: fade LONG tetap hidup di 1h netral', any(s[1]=='L' and s[3]=='fade' for s in htf_case('fade',10.0,11.0)))
# v7.1: konflik fade LONG vs scalp SHORT di bar washout — fade menang, sinyal gak dibuang
res=htf_case('fade',12.0,11.0)
check('v7.1 konflik fade vs scalp: fade menang (sinyal hidup)', any(s[1]=='L' and s[3]=='fade' for s in res), str(res))
# v9.0 SUPER MONEY FLOW: vol BTC meledak (btcv>=1.5) + RSI6 lembah -> fade grade B naik grade A
kf=base_kk(300)
for j in range(100,297): kf[j][4]=100+(0.5 if j%2 else -0.5)
kf[297]=[297*300000, 99.0, 99.5, 87.0, 92.0, 12.0]   # climax tapi volume tipis (volx ~1.2 -> grade B)
cf=[r[4] for r in kf]; rf=rb.rsi6(cf); zf=rb.zscore(cf)
vf=[r[5] for r in kf]; vmf=[0.0]*len(vf)
for i in range(20,len(vf)): vmf[i]=sum(vf[i-20:i])/20
htfF=[(12.0,11.0)]*len(kf)
base=[s for s in hr.gen_hybrid(kf,rf,zf,vmf,htfF,'RANGING') if s[3]=='fade']
boost=[s for s in hr.gen_hybrid(kf,rf,zf,vmf,htfF,'RANGING',btcv=2.0) if s[3]=='fade']
check('v9.0 superflow: fade grade B tanpa suntikan BTC', base and base[0][2]=='B', str(base))
check('v9.0 superflow: suntikan BTC vol>=1.5 + RSI6 lembah -> grade A', boost and boost[0][2]=='A', str(boost))
# fail-closed: data HTF None = non-fade diblok
k=base_kk(300)
for j in range(2):
    k[296-j]=[(296-j)*300000, 100.5, 100.8, 99.8, 99.0, 10.0]
k[297]=[297*300000, 99.5, 102.5, 99.4, 102.3, 25.0]
cc=[r[4] for r in k]; rr=rb.rsi6(cc); z=rb.zscore(cc)
vv=[r[5] for r in k]; vm=[0.0]*len(vv)
for i in range(20,len(vv)): vm[i]=sum(vv[i-20:i])/20
check('HTF fail-closed: data None = non-fade diblok', not any(s[1]=='L' for s in hr.gen_hybrid(k,rr,z,vm,[None]*300,'RANGING')),
      str(hr.gen_hybrid(k,rr,z,vm,[None]*300,'RANGING')))

# ---------- 5. TYPE-GUARD BOS v7 (offline, _req di-mock) ----------
_orig=jb._req; jb.KEY='test-key-offline'
jb._req=lambda p: {'answers':{'decision':{'choice':'CONFIRMED_NORMAL','probabilities':{'CONFIRMED_NORMAL':0.8,'REJECT':0.2},'confidence':0.8}}}
r=jb.call_jev({'symbol':'BTCUSDT','side':'LONG','mss':'MSS_BULLISH','engine':'scalp'})
check('type-guard CONFIRMED_NORMAL', r['decision']=='CONFIRMED' and r['variant']=='NORMAL', str(r))
jb._req=lambda p: {'answers':{'decision':{'choice':'MAYBE','probabilities':{},'confidence':0.5}}}
r=jb.call_jev({'symbol':'BTCUSDT','side':'LONG'})
check('type-guard choice asing -> REJECT', r['decision']=='REJECT' and 'cacat' in r.get('reason',''), str(r))
jb._req=lambda p: {'answers':{'decision':{'choice':'REJECT','probabilities':{'REJECT':0.9},'confidence':0.9}}}
r=jb.call_jev({'symbol':'XAUUSDT','side':'SHORT'})
check('REJECT sah dgn prob', r['decision']=='REJECT' and r['probs'].get('REJECT')==0.9, str(r))
jb._req=_orig
check('v12.0 persona verbatim (THE TRUE SCALPER GOD + GOD MINDSET v12.0)', 'GOD MINDSET v12.0' in jb.SYSTEM_IMMUNITY and 'THE TRUE SCALPER GOD v12.0' in jb.PERSONA_V7 and 'SCALPER sungguhan' in jb.SYSTEM_IMMUNITY)
check('criteria 4 opsi', list(jb.CRITERIA)==['CONFIRMED_TIGHT','CONFIRMED_NORMAL','CONFIRMED_WIDE','REJECT'])
# v7.1 ANTI-CHASE COMPILER GUARD
# v9.0: persona diganti verbatim (directive) — guard anti-chase tinggal di CRITERIA/kode enforcer
_jsrc=open(jb.__file__).read()
check('v7.2.2 FINAL-SEAL fade 3-syarat di KODE enforcer (bukan cuma persona)', 'INVALID_FADE_NO_CLIMAX_VOLUME' in _jsrc and 'MISSING_STRUCTURE_CONFIRMATION' in _jsrc)
check('v7.1 REJECT criteria sebut CHASE', 'CHASE' in jb.CRITERIA['REJECT'] and 'WAIT_FOR_RETRACE_TO_FVG' in jb.CRITERIA['REJECT'])
# v7.2 FINAL SEAL: HARD RULE MSS
# v9.0: FINAL SEAL bukan lagi di persona — persona predator + seal tetap di kode
check('v12.0 persona lensa lembah/pucuk RSI6 (<= 20 LEMBAH / >= 80 PUCUK) verbatim', 'metrics.rsi6Realtime' in jb.PERSONA_V7 and 'LEMBAH' in jb.PERSONA_V7 and 'PUCUK' in jb.PERSONA_V7)
check('v7.2 REJECT criteria sebut MISSING_STRUCTURE', 'MISSING_STRUCTURE_CONFIRMATION' in jb.CRITERIA['REJECT'])
jb._req=lambda p: {'answers':{'decision':{'choice':'CONFIRMED_NORMAL','probabilities':{'CONFIRMED_NORMAL':0.9},'confidence':0.9}}}
r=jb.call_jev({'symbol':'INJUSDT','side':'LONG','mss':'NONE','engine':'scalp'})
check('v7.2 host-guard: mss NONE + scalp CONFIRMED -> dibuang REJECT', r['decision']=='REJECT' and 'FINAL-SEAL' in r.get('reason',''), str(r))
r=jb.call_jev({'symbol':'WIFUSDT','side':'LONG','mss':'','engine':'trend','asset':{'rsi6Realtime':55}})
check('v7.2 host-guard: mss kosong + trend -> REJECT juga', r['decision']=='REJECT', str(r))
r=jb.call_jev({'symbol':'XAGUSDT','side':'SHORT','mss':'NONE','engine':'fade','metrics':{'rsi6Realtime':88,'volx':3.5,'wick_ratio_pct':{'low':2.0,'high':53.0}}})
check('v7.2.2 pengecualian fade PENUH (RSI6 88 + volx 3.5 + wick 53%) lolos', r['decision']=='CONFIRMED' and r['variant']=='NORMAL', str(r))
r=jb.call_jev({'symbol':'APTUSDT','side':'LONG','mss':'NONE','engine':'fade','metrics':{'rsi6Realtime':14.0,'volx':0.8,'wick_ratio_pct':{'low':53.0,'high':1.5}}})
check('v7.2.2 fade volx 0.8 (<1.2) -> REJECT INVALID_FADE_NO_CLIMAX_VOLUME', r['decision']=='REJECT' and 'INVALID_FADE_NO_CLIMAX_VOLUME' in r.get('reason',''), str(r))
r=jb.call_jev({'symbol':'APTUSDT','side':'LONG','mss':'NONE','engine':'fade','metrics':{'rsi6Realtime':14.0,'volx':3.5,'wick_ratio_pct':{'low':20.0,'high':1.5}}})
check('v7.2.2 fade wick 20% (<40) -> REJECT INVALID_FADE_NO_CLIMAX_VOLUME', r['decision']=='REJECT' and 'INVALID_FADE_NO_CLIMAX_VOLUME' in r.get('reason',''), str(r))
r=jb.call_jev({'symbol':'XAGUSDT','side':'SHORT','mss':'NONE','engine':'fade','asset':{'rsi6Realtime':88}})
check('v7.2.2 fade TANPA data climax -> fail-closed REJECT (bukan lolos)', r['decision']=='REJECT', str(r))
r=jb.call_jev({'symbol':'BTCUSDT','side':'LONG','mss':'NONE','engine':'fade','metrics':{'rsi6Realtime':55,'volx':3.5,'wick_ratio_pct':{'low':53.0,'high':1.5}}})
check('v7.2.2 fade RSI6 netral (55) -> REJECT (syarat RSI6 ekstrem tetap)', r['decision']=='REJECT' and 'FINAL-SEAL' in r.get('reason',''), str(r))
r=jb.call_jev({'symbol':'ADAUSDT','side':'LONG','mss':'MSS_BULLISH','engine':'trend'})
check('v7.2 mss ada -> CONFIRMED utuh', r['decision']=='CONFIRMED', str(r))
jb._req=_orig

# ---------- 5b. v8.0 PURE ATR ADAPTIVE SCALPER ----------
check('v12.0 CRITERIA: angka fiksi & P8 hantu musnah, TP band disebut milik eksekutor', '0.6%' not in jb.CRITERIA['CONFIRMED_TIGHT'] and 'P8 internal' not in ''.join(jb.CRITERIA.values()) and 'pipeline 1-8' not in ''.join(jb.CRITERIA.values()) and 'eksekutor yang menyesuaikan' in jb.CRITERIA['CONFIRMED_WIDE'])
check('v12.0 persona anti-fakeout (closePos 50 = leleh, FAKEOUT REJECT) verbatim', 'closePos dekat 50' in jb.PERSONA_V7 and 'FAKEOUT' in jb.PERSONA_V7 and 'retracePct' in jb.PERSONA_V7)
_t=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live.py')).read()
_t=re.sub(r'"""[\s\S]*?"""', ' ', _t); _t=re.sub(r'#.*', '', _t)
check('v8.0 executor: multiplier statis musnah', 'SL_PCT*0.5' not in _t and 'SL_PCT*0.67' not in _t and 'SL_PCT*1.5, 2.5' not in _t)
check('v11.0 executor: TIGHT 0.50x + RR 2.5 (pre-emptive pucuk)', '_atr_f * 0.50' in _t and 'tp_rr = 2.5' in _t and '_atr_f * 0.75' not in _t)
check('v8.0 executor: ATR widening-only P32 musnah (ATR = basis mutlak)', '_sug_f>sl_pct' not in _t and '_P32_ATR_SL' not in _t)
check('v8.0 TP_RR_CHOP/TREND kode mati dihapus', 'TP_RR_CHOP' not in _t and 'TP_RR_TREND' not in _t)
# ---------- 5c. v9.0 TRADING GOD ENGINE ----------
check('v9.0 P36 clamp statis musnah', 'max(0.003,min(0.030,sl_pct))' not in _t and 'P36 SANITY' not in _t)
check('v9.0 P19 range-guard musnah (SL murni ATR linear)', 'range_guard_wide' not in _t and 'P19 RANGE-POSITION' not in _t)
check('v9.0 Super Money Flow: helper + wiring ke gen_hybrid', 'def smc_btc_volume' in _t and 'btcv=smc_btc_volume()' in _t)
_exp=os.path.join(os.path.dirname(os.path.abspath(__file__)),'.env.example')
if not os.path.exists(_exp): _exp=os.path.join(os.path.dirname(os.path.abspath(__file__)),'test-bot','.env.example')
_ex=open(_exp).read()
check('v12.3.4 TRAIL_ACT balik 0.004 / TRAIL_DIST 0.002 (.env.example)', 'TRAIL_ACT=0.004' in _ex and 'TRAIL_DIST=0.002' in _ex)
# ---------- 5d. v10.0 PURE UNCLAMPED ATR (kurir bebas clamp) ----------
_ms=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'market_snapshot.py')).read()
check('v10.0 kurir: clamp 0.8-2.4% MUSNAH (sl_pct = 1.5xATR murni)', 'max(0.8,min(2.4' not in _ms and "sl_pct=1.5*m['atr_pct']" in _ms)
check('v10.0 kurir: floor teknis pasar mati (sl_pct<0.20 -> 0.25)', 'if sl_pct<0.20: sl_pct=0.25' in _ms)
check('v10.0 executor: fallback 1.2% cuma utk data kosong (tetap)', '_atr_f = float(_ss.get(\'sl_pct_suggest\') or 1.2) / 100.0' in _t)
# ---------- 5e. v10.1 ARCHITECTURE RE-ALIGNMENT ----------
check('v12.0 instruksi bos = lensa anti-fakeout + lembah/pucuk (instruksi v10.1 musnah)', 'lensa anti-fakeout' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'jev_bridge.py')).read()
      and 'Jalankan analisis penentuan arah' not in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'jev_bridge.py')).read())
check('v10.1 docstring stale pipeline_log musnah (jev_bridge)', 'pipeline_log' not in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'jev_bridge.py')).read())
# ---------- 5f. v10.1.1 FINAL POLISH (branding) ----------
_tg=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'tg_notify.py')).read()
check('v12.3 panel BOT START = TYPESAFE SNIPER v12.3 TRUE SCALPER', 'TYPESAFE SNIPER v12.3 TRUE SCALPER' in _tg and 'PRE-EMPTIVE' not in _tg.split('TYPESAFE SNIPER')[1][:60])
check('v10.1.1 label P1→P8 musnah, ganti ANALISA v10.1', 'P1→P8' not in _tg and 'ANALISA · PURE ATR' in _tg and 'SUPER MONEY FLOW' in _tg)
# ---------- 5g. v11.0 PRE-EMPTIVE PREDATOR ----------
check('v11.0 kurir: PRE-EMPTIVE PEAK DETECTOR di gen_hybrid', '_preemptive' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read()
      and "r6>=88 and _volx>=1.5 and _wick_top>=35.0" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read()
      and "r6<=12 and _volx>=1.5 and _wick_bot>=35.0" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read())
check('v11.0 kurir: bypass HTF utk jalur pre-emptive (engine lain fail-closed tetap)', 'if not _preemptive:' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read())
check('v11.0 enforcer: override A+ -> CONFIRMED TIGHT (sebelum FINAL SEAL)', 'PRE-EMPTIVE COPET v11.0' in _jsrc and "_grade=='A+'" in _jsrc)
check('v11.0 resolusi konflik: A+ tidak ditimpa A/B', "if any(s[1] == 'A+' for s in ss):" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read())
# perilaku: fixture SHORT pucuk absolut (RSI6 96, volx 4.1, wick atas ~79%) -> A+ meski HTF None
_k=[[i*300000, 100.0, 100.2, 99.8, 100.0, 10.0] for i in range(300)]
for _j in range(292, 297):
    _cc=100+(_j-291)*0.8; _k[_j]=[_j*300000, _cc-0.3, _cc+0.4, _cc-0.5, _cc, 14.0]
_k[297]=[297*300000, 103.4, 106.5, 103.2, 103.9, 45.0]
_cc=[r[4] for r in _k]; _rs=rb.rsi6(_cc); _zz=rb.zscore(_cc)
_vv=[r[5] for r in _k]; _vm=[0.0]*300
for _i2 in range(20,300): _vm[_i2]=sum(_vv[_i2-20:_i2])/20
_sig=hr.gen_hybrid(_k,_rs,_zz,_vm,[None]*300,None,btcv=None)   # HTF None + struct None!
check('v11.0 perilaku: pucuk absolut (RSI6 96/volx 4.1/wick 79%) -> A+ walau HTF None', any(s[1]=='S' and s[2]=='A+' for s in _sig), str(_sig))
jb._req=lambda p: {'answers':{'decision':{'choice':'REJECT','probabilities':{'REJECT':0.9},'confidence':0.5}}}   # bos nolak pun, A+ wajib menang (override)
_r=jb.call_jev({'symbol':'GALAUSDT','side':'SHORT','grade':'A+','mss':'NONE','engine':'fade'})
check('v11.0 perilaku: enforcer A+ mss NONE -> CONFIRMED TIGHT (override menang dr bos REJECT)', _r['decision']=='CONFIRMED' and _r['variant']=='TIGHT', str(_r))
jb._req=lambda p: {'answers':{'decision':{'choice':'CONFIRMED_NORMAL','probabilities':{'CONFIRMED_NORMAL':0.6},'confidence':0.6}}}
_r2=jb.call_jev({'symbol':'GALAUSDT','side':'SHORT','grade':'A','mss':'NONE','engine':'fade','metrics':{'rsi6Realtime':55,'volx':2.0,'wick_ratio_pct':{'low':10.0,'high':60.0}}})
check('v11.0 seal tetap: grade A + fade non-ekstrem + mss NONE -> REJECT', _r2['decision']=='REJECT', str(_r2))
_hrsrc=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read()
check('v11.0 wiring: gen_hybrid tanpa slot mati extra_engines + dipanggil dgn btcv=btcv', 'extra_engines' not in _hrsrc
      and 'gen_hybrid(kk,rs,zz,vsma,htf15,maps[\'1h_struct\'],btcv=btcv)' in _t)
# ---------- 5h. v12.0 TRUE SCALPER GOD ----------
_tsk=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_skill.py')).read()
check('v12.0 kurir: anti-fakeout lens di payload (closePos/retracePct/bbTouch/consec/candleAna)',
      all(k in _tsk for k in ('candleAna','closePos','consec','retracePct','bbTouch')))
check('v12.0 executor: TP BAND 0.6-1.5% kontrak (SL ATR murni gak disentuh)',
      'if tp_pct<0.006: tp_d=entry*0.006' in _t and 'elif tp_pct>0.015: tp_d=entry*0.015' in _t
      and 'sl_pct = _atr_f * 0.50' in _t and 'max(0.003' not in _t and 'min(0.030' not in _t)
check('v12.0 executor: log atr_sl mult TIGHT 0.50 sinkron kenyataan',
      "{'TIGHT':0.50," in _t and "{'TIGHT':0.75," not in _t)
def _mkser():
    # i=len(kk)-2 -> bar event = index 58 (bar closed terakhir); index 59 cuma filler
    ser=[[k*300000, 99+(0.02 if k%2 else -0.02), 99.03, 98.97, 99+(0.02 if k%2 else -0.02), 10.0] for k in range(60)]
    ser[58]=[58*300000, 99.0, 101.0, 98.0, 100.6, 10.0]      # bar closed: close dekat high
    return ser
_m=ds.build_payload_v7('X',_mkser(),'SHORT','A','fade','RANGE',0.0,{'15m':{},'1h':{}})
check('v12.0 perilaku kurir: lens menghitung benar (SHORT, closePos 86.7, BB upper, retrace>0)',
      abs(_m['metrics']['closePos']-86.7)<0.5 and _m['metrics']['bbTouch']=='UPPER'
      and _m['metrics']['candleAna']>50 and _m['metrics']['retracePct']>0
      and _m['metrics']['consec']==1, str(_m['metrics']))
def _mkser2():
    ser=_mkser()
    ser[58]=[58*300000, 99.0, 99.2, 97.0, 97.4, 10.0]         # bar closed: close dekat low
    return ser
_m2=ds.build_payload_v7('X',_mkser2(),'LONG','A','fade','RANGE',0.0,{'15m':{},'1h':{}})
check('v12.0 perilaku kurir: LONG closePos 18.2 + bbTouch LOWER + candleAna negatif',
      abs(_m2['metrics']['closePos']-18.2)<0.5 and _m2['metrics']['bbTouch']=='LOWER'
      and _m2['metrics']['candleAna']<-50, str(_m2['metrics']))
# ---------- 5i. v12.2 GODMODE SENSOR (port v15-pro-genius/godmode_v2_engine) ----------
import importlib.util as _iu
_gspec=_iu.spec_from_file_location('gmv2',os.path.join(os.path.dirname(os.path.abspath(__file__)),'gmv2.py'))
_gm=_iu.module_from_spec(_gspec); _gspec.loader.exec_module(_gm)
check('v12.2 gmv2: bobot & tier verbatim GMV2 asli', _gm.FEATURE_WEIGHTS=={"trend":25,"momentum":20,"mtf_alignment":15,"liquidity":15,"volume":10,"volatility":10,"session":5}
      and _gm.TIER_THRESHOLDS=={"sniper":90,"execute":75,"watch":71,"reject":0})
check('v12.2 gmv2: 2 set bobot TREND vs MEAN_REVERSION verbatim', _gm.MEAN_REVERSION_WEIGHTS=={"trend":5,"momentum":30,"mtf_alignment":5,"liquidity":30,"volume":10,"volatility":10,"session":10})
_fgm=_gm.compute_features(_mkser(),None)
check('v12.2 gmv2: fitur lengkap 7 grup', _fgm is not None and all(k in _fgm for k in ('trend_score','rsi5','stoch_k','mtf_alignment_score','near_support','near_resistance','atr_pct','volume_ratio','session_score')))
_sgm,_tgm,_bdm=_gm.score(_fgm,'LONG')
check('v12.2 gmv2: skor 0-100 + tier valid + breakdown 7 dimensi', 0<=_sgm<=100 and _tgm in ('SNIPER','EXECUTE','WATCH','REJECT') and len([k for k in _bdm if k!='setup_type'])==7)
_gbf=_gm.best_for([[k*300000,100,100.1,99.9,100+(0.05 if k%2 else -0.02),10.0] for k in range(60)],None)
check('v12.2 gmv2: best_for balikkin arah+skor', _gbf is not None and _gbf['best'] in ('LONG','SHORT','NEUTRAL') and 0<=_gbf['score']<=100)
check('v12.2 wiring: kurir evaluate + brief.godmode + notif GODMODE + bos kompas',
      'gmv2.evaluate(kk[:i+1]' in _t and "brief['godmode']" in _t and "'godmode':_br.get('godmode')" in _t
      and 'GODMODE:' in _tg and 'Payload.godmode = sensor' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'jev_bridge.py')).read())
check('v12.2 kurir: closes 15m di-stash build_htf_maps (tanpa fetch ekstra)', "maps['c15']" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hybrid_rules.py')).read())

# ---------- 6. PAYLOAD KONTRAK v7 ----------
ds.btc_bias=lambda: {'bias':'UP','b5':'UP','b1':'UP'}
kk=base_kk(600)
kk[-2]=[598*300000, 99.0, 99.5, 89.0, 92.0, 60.0]
maps={'15m':{kk[-2][0]:(1.1,1.0)},'1h':{kk[-2][0]:(1.1,1.0,1.7)},'1h_struct':'BULLISH_CONTINUATION'}
p=ds.build_payload_v7('BTCUSDT',kk,'L','A','fade','RANGE',0.0001,maps)
check('payload asset.class', p['asset']['class']=='CRYPTO' and p['asset']['ticker']=='BTC')
check('payload HTF', p['higher_tf_alignment']['tf_15m_ema_cross']=='BULLISH' and p['higher_tf_alignment']['vol_x_1h']==1.7)
check('payload macro', p['macro_matrix']['btc_bias']=='UP')
check('payload metrics', p['metrics']['volx'] is not None and 'zScore' in p['metrics'] and 'wick_ratio_pct' in p['metrics'])
check('v7.1 payload metrics anti-chase fields', 'entryStatus' in p['metrics'] and 'atrDistance' in p['metrics'])
check('payload engine+side', p['engine']=='fade' and p['side']=='LONG')
pm=ds.build_payload_v7('XAUUSDT',kk,'S','A','fade','RANGE',0.0,maps)
check('payload metal', pm['asset']['class']=='TRADFI_METAL' and pm['asset']['ticker']=='XAUUSD')

# ---------- 7. STATIC: kode mati era lama GAK BOLEH balik ----------
def grep(fname, *pats):
    t=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),fname)).read()
    t=re.sub(r'"""[\s\S]*?"""', ' ', t)   # buang docstring
    t=re.sub(r"#.*", '', t)                   # buang komentar
    return {p: len(re.findall(rf'\b{re.escape(p)}\b', t)) for p in pats if re.search(rf'\b{re.escape(p)}\b', t)}
dead=grep('dewa_live.py','MIN_CONF','P6_LOOSE','momentumBattery','reversal_hint','pipeline_log','tv_ta','_p38_dry_pass','skip_dry','battery','vision','rubric','build_extras','BE_TRIG','BE_OFF','_flipped','wick_flip')
check('dewa_live bersih kode mati', not dead, str(dead))
# v7.1: wick-flip P16-B DIMUSNAHKAN — flip arah mekanis gak boleh balik lagi
t_live=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live.py')).read()
check('v7.1 wick-flip musnah total', 'wick_flip' not in t_live and 'WICK-FLIP' not in t_live and "_flipped" not in t_live)
# v7.1.1 CLEANUP: dedup intra-batch + notional dinamis + env OVERRIDE
check('v7.1.1 dedup intra-batch pending_sides', 'pending_sides' in t_live and '20.0/' not in t_live)
t_tg=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'tg_notify.py')).read()
t_tg_code=re.sub(r'"""[\s\S]*?"""', ' ', t_tg)   # buang docstring sblm grep (lesson: kata kunci di docstring)
t_tg_code=re.sub(r'#.*', '', t_tg_code)
check('v7.1.1 tg_notify env OVERRIDE (P35, tanpa setdefault)', 'setdefault' not in t_tg_code and 'os.environ[k.strip()]=v.strip()' in t_tg_code)
dead=grep('dewa_skill.py','build_extras','classify_momentum','enrich_briefing','obv_slope','kdj','stoch_rsi','rel_strength','spark(')
check('dewa_skill bersih scalper pack', not dead, str(dead))
dead=grep('hybrid_rules.py','gen_loose_fade','p6')
check('hybrid_rules bersih P6', not dead, str(dead))
dead=grep('smc_engine.py','momentum_battery','reversal_hint','pipeline_log')
check('smc_engine bersih battery/hint', not dead, str(dead))
dead=grep('reversion_bot.py','gen_signals','simulate','imb')
check('reversion_bot tinggal primitif', not dead, str(dead))
# RSI(6) MANDATE: gak ada RSI 14 di pipeline inti
for f in ('hybrid_rules.py','dewa_skill.py','reversion_bot.py','dewa_live.py'):
    t=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),f)).read()
    check(f'RSI6-only {f}', 'rsi14' not in t and 'rsi(14' not in t.lower() and 'RSI(14' not in t)

# ---------- 8. P39 TRIM (dipertahankan dari test_p39) + P35 NO-FALLBACK (dari test_p32) ----------
check('p39 trim: cap 2000 by bar_ts', len(hr._p39_trim if hasattr(hr,'_p39_trim') else __import__('dewa_live')._p39_trim(
    {(f'S{i}', i*1, 'L') for i in range(3000)})) == 2000)
import dewa_live as dl
_trim=dl._p39_trim({('A', 100, 'L'), ('B', 200, 'S'), ('C', 50, 'L')})
check('p39 trim: keep newest, drop oldest', [k[0] for k in sorted(_trim, key=lambda x: x[1])] == ['C','A','B'], str(_trim))
check('p39 trim: under cap utuh', len(dl._p39_trim({('A',1,'L'),('B',2,'S')})) == 2)
# hygiene: redirect log produksi sebelum uji llm_call
import tempfile
dl.LOG=os.path.join(tempfile.gettempdir(),'test_v7_dl.jsonl')
try: os.remove(dl.LOG)
except Exception: pass
_orig_req=jb._req
def _boom(p): raise RuntimeError('conn refused (test)')
jb._req=_boom
r=dl.llm_call({'symbol':'BTCUSDT','side':'LONG'})
check('P35 no-fallback: jev mati = REJECT jev_err', r.get('decision')=='REJECT' and str(r.get('reason','')).startswith('jev_err'), str(r))
check('P35 no-fallback: gak ada model kedua', 'fallback' not in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'jev_bridge.py')).read().lower().replace('no-fallback','').replace('tanpa fallback',''))
check('jev402_hit: Jev402 terdeteksi', dl.jev402_hit(jb.Jev402('x')) is True)
check('jev402_hit: string 402 terdeteksi', dl.jev402_hit(Exception('HTTP 402 Payment Required')) is True)
check('jev402_hit: error biasa bukan 402', dl.jev402_hit(Exception('HTTP 429 too many')) is False)
jb._req=_orig_req

# ---------- 9. v7.2.1 STRICT MSS — ATR BARRIER ----------
# CATATAN FORMAT: kk utk detect_mss = [o,h,l,c,v] (5 elemen, TANPA ts — sama spt smc_engine.klines()).
_base=[[99.9,100.1,99.7,99.9,10.0] for i in range(30)]   # flat, ATR~0.44 (TR=0.4/bar), swing high fractal=100.1
_big=_base[:]+[[100.0,100.95,99.9,100.85,50.0]]          # close 100.85 -> pen 0.75 >= 0.25*ATR(0.446)
_r=smc.detect_mss(_big)
check('v7.2.1 ATR barrier: pen 0.75 (>=0.25xATR) = MSS_BULLISH sah', _r['mss']=='MSS_BULLISH', str(_r))
_tiny=_base[:]+[[99.9,100.2,99.8,100.12,50.0]]           # pen 0.02 << barrier (INJ 3-tick style)
_r=smc.detect_mss(_tiny)
check('v7.2.1 ATR barrier: pen secuil = NONE (MSS palsu dibuang)', _r['mss']=='NONE', str(_r))
_short=_base[:8]+[[99.9,101.5,99.8,101.3,50.0]]           # 9 bar -> ATR tak cukup
_r=smc.detect_mss(_short)
check('v7.2.1 ATR barrier: data <15 bar = fail-closed NONE', _r['mss']=='NONE', str(_r))

# ---------- 10. v12.3 FRESH RE-CHECK + SL FLOOR POST-MULT ----------
# (a) P12-LIVE: LONG dilarang saat RSI6 live > 85 (pucuk tersembunyi setelah bar sinyal)
_kk=[[0,100+i*0.1,100.1+i*0.1,99.9+i*0.1,100.0+i*0.1,10.0] for i in range(59)]
cd={'sym':'TESTUSDT','side':'L','grade':'A','src':'trend'}
_r=hr.fresh_recheck(cd, {'TESTUSDT':_kk}, rb, px=105.9)
check('v12.3 P12-LIVE: LONG dgn RSI6 live >85 = block', _r['ok'] is False and 'P12-LIVE' in _r['why'], str(_r))
# (b) A+ STALENESS: SHORT pre-emptive pas pucuknya udah basi (RSI live turun ke 15-80) = block
_kd=[[0,110-i*0.05,110.05-i*0.05,109.95-i*0.05,110.0-i*0.05,10.0] for i in range(57)]
_kd=_kd+[[0,109.5,109.55,108.95,109.0,10.0],[0,109.0,109.05,108.45,108.5,10.0]]
cd={'sym':'TESTUSDT','side':'S','grade':'A+','src':'fade'}
_r=hr.fresh_recheck(cd, {'TESTUSDT':_kd}, rb, px=108.4)
check('v12.3 A+ staleness: SHORT A+ pas pucuk basi (RSI live <80) = block', _r['ok'] is False and 'BASI' in _r['why'], str(_r))
# (c) fade sehat: ekor jenuh >= 25% = lolos tanpa demote (kasus LTC/SUI fade valid)
_kb=[[0,100.0,100.02,99.98,100.0,10.0] if i%2==0 else [0,100.01,100.03,99.99,100.01,10.0] for i in range(58)]
_kb=_kb+[[0,100.0,100.05,98.0,99.9,10.0]]
cd={'sym':'TESTUSDT','side':'L','grade':'A','src':'fade'}
_r=hr.fresh_recheck(cd, {'TESTUSDT':_kb}, rb, px=None)
check('v12.3 fade sehat: ekor jenuh >=25% = lolos (bos tetap ditanya)', _r['ok'] is True and _r['demote'] is False, str(_r))
# (d) FADE-DEMOTE: climax hilang (bar live marubozu tanpa ekor) = demote B, bukan REJECT paksa
_km=[[0,100.0,100.02,99.98,100.0,10.0] if i%2==0 else [0,100.01,100.03,99.99,100.01,10.0] for i in range(58)]
_km=_km+[[0,100.0,100.95,99.95,100.9,10.0]]
cd={'sym':'TESTUSDT','side':'L','grade':'A','src':'fade'}
_r=hr.fresh_recheck(cd, {'TESTUSDT':_km}, rb, px=None)
check('v12.3 fade-demote: climax hilang = demote B dgn alasan ekor <25%', _r['ok'] is True and _r['demote'] is True and '25%' in _r['demote_why'], str(_r))
# (e) regression lens: rb.rsi6 menerima closes+float live (silent-kill [[...]] MUSNAH)
_r6=rb.rsi6([float(x[4]) for x in _kk]+[101.0])[-1]
check('v12.3 lens math: rsi6(closes + float tick) jalan', _r6 is not None and 0<=_r6<=100, str(_r6))
# (f) wiring & floor via source-check (bukan import ulang dewa_live)
_src=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live.py')).read()
check('v12.3.2 SL floor 1.5% ditagih POST-mult', 'sl_pct = max(sl_pct, 0.015)' in _src, '')
check('v12.3.3 notif: engine fade/scalp/trend diteruskan ke fmt_open (DRY+LIVE)', _src.count("'engine':cd.get('src')")==2, '')
check('v12.3 silent-kill lens MUSNAH (tanpa list nyempul di CALL)', '+[[0,0,0,0,_px,0]])' not in _src and '+[_px])' in _src, '')
check('v12.3 wiring fresh_recheck sebelum llm_call', 0<_src.find('hr.fresh_recheck(cd')<_src.find('d=llm_call('), '')
check('v12.3 log audit: final_sl_pct + rsi_now di decision', "'final_sl_pct'" in _src and "'rsi_now':_rc.get('rsi_now')" in _src, '')

print(f"\n===== test_v7: {PASS} pass / {FAIL} fail =====")
sys.exit(1 if FAIL else 0)
