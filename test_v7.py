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
check('scalp v7.1: volx<1.2 ditolak', not scalp_case(99.5,102.5,99.4,102.3,11.0,reds=2))
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
check('HTF: scalp LONG butuh EMA20>E50 15m', not htf_case('scalp',10.0,11.0), str(htf_case('scalp',10.0,11.0)))
check('HTF: scalp LONG lolos EMA20>E50', any(s[1]=='L' and s[3]=='scalp' for s in htf_case('scalp',12.0,11.0)), str(htf_case('scalp',12.0,11.0)))
check('HTF: 1h BEARISH_EXTREME blok LONG non-fade', not htf_case('scalp',12.0,11.0,'BEARISH_EXTREME_DUMP'))
check('HTF: fade LONG DIKECUALIKAN dr filter', any(s[1]=='L' and s[3]=='fade' for s in htf_case('fade',10.0,11.0,'BEARISH_EXTREME_DUMP')),
      str(htf_case('fade',10.0,11.0,'BEARISH_EXTREME_DUMP')))
# v7.1: konflik fade LONG vs scalp SHORT di bar washout — fade menang, sinyal gak dibuang
res=htf_case('fade',12.0,11.0)
check('v7.1 konflik fade vs scalp: fade menang (sinyal hidup)', any(s[1]=='L' and s[3]=='fade' for s in res), str(res))
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
check('persona v7 verbatim', 'DILARANG KERAS' in jb.SYSTEM_IMMUNITY and 'TYPESAFE SNIPER v7.0' in jb.PERSONA_V7 and '8 LANGKAH' in jb.PERSONA_V7 and 'P8' in jb.PERSONA_V7)
check('criteria 4 opsi', list(jb.CRITERIA)==['CONFIRMED_TIGHT','CONFIRMED_NORMAL','CONFIRMED_WIDE','REJECT'])
# v7.1 ANTI-CHASE COMPILER GUARD
check('v7.1 anti-chase di P5 persona', 'ANTI-CHASE' in jb.PERSONA_V7 and 'WAIT_FOR_RETRACE_TO_FVG' in jb.PERSONA_V7
      and '3.0 ATR' in jb.PERSONA_V7 and 'entryStatus' in jb.PERSONA_V7)
check('v7.1 REJECT criteria sebut CHASE', 'CHASE' in jb.CRITERIA['REJECT'] and 'WAIT_FOR_RETRACE_TO_FVG' in jb.CRITERIA['REJECT'])
# v7.2 FINAL SEAL: HARD RULE MSS
check('v7.2 FINAL SEAL di P4 persona', 'FINAL SEAL' in jb.PERSONA_V7 and 'MISSING_STRUCTURE_CONFIRMATION' in jb.PERSONA_V7
      and 'rsi6Realtime < 20' in jb.PERSONA_V7)
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

# ---------- 5b. v7.3 SCALP-LOCK DYNAMIC ----------
check('v7.3 CRITERIA TIGHT scalp (SL 0.6%/TP 1.5%, RR 1:2.5)', '0.6%' in jb.CRITERIA['CONFIRMED_TIGHT'] and '1.5%' in jb.CRITERIA['CONFIRMED_TIGHT'] and '1:2.5' in jb.CRITERIA['CONFIRMED_TIGHT'])
check('v7.3 CRITERIA NORMAL scalp (SL 0.8%/TP 2.0%)', '0.8%' in jb.CRITERIA['CONFIRMED_NORMAL'] and '2.0%' in jb.CRITERIA['CONFIRMED_NORMAL'])
check('v7.3 CRITERIA WIDE scalp (SL 1.2%/TP 3.0%)', '1.2%' in jb.CRITERIA['CONFIRMED_WIDE'] and '3.0%' in jb.CRITERIA['CONFIRMED_WIDE'])
check('v7.3 persona P7 SCALP-LOCK + TRAIL-LOCK >= 0.6%', 'SCALP-LOCK DYNAMIC' in jb.PERSONA_V7 and 'TRAIL-LOCK' in jb.PERSONA_V7 and '>= 0.6%' in jb.PERSONA_V7)
_t=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live.py')).read()
_t=re.sub(r'"""[\s\S]*?"""', ' ', _t); _t=re.sub(r'#.*', '', _t)
check('v7.3 executor: angka TP lama (RR 4.0) musnah', '1.5, 4.0' not in _t)
check('v7.3 executor map TIGHT 0.5/NORMAL 0.67/WIDE 1.0 — RR semua 2.5', 'SL_PCT*0.5, 2.5' in _t and 'SL_PCT*0.67, 2.5' in _t and 'SL_PCT, 2.5' in _t)

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

print(f"\n===== test_v7: {PASS} pass / {FAIL} fail =====")
sys.exit(1 if FAIL else 0)
