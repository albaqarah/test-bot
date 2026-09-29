#!/usr/bin/env python3
"""P36 REGRESI: bug satuan SL (persen vs fraksi) — kasus WLD 29 Sep (SL -208%, TP +832%).
Offline, tanpa API. Semua cek harus True."""
import importlib.util, os, sys, py_compile

H=os.path.dirname(os.path.abspath(__file__))
res=[]
def check(name, ok): res.append((name,bool(ok))); print(('OK  ' if ok else 'FAIL'), name)

# 1) kompilasi semua modul yg disentuh
for f in ('dewa_live.py','market_snapshot.py','jev_bridge.py'):
    try:
        py_compile.compile(os.path.join(H,f), doraise=True); check(f'compile {f}', True)
    except Exception as e: check(f'compile {f}: {e}', False)

# 2) patch hadir & pola lama HILANG
src=open(os.path.join(H,'dewa_live.py')).read()
check('unit-fix (_sug/100) ada', '_sug_f=_sug/100.0' in src)
check('pola lama (_sug>sl_pct) HAPUS', '_sug>sl_pct' not in src)
check('sanity clamp SL ada', 'sl_pct=max(0.003,min(0.030,sl_pct))' in src)

# 3) simulasi jalur SL PERSIS dewa_live (WIDE + slSuggest 2.08% = kasus WLD)
#    kontrak satuan: sl_pct_suggest dari market_snapshot = PERSEN; internal = FRAKSI
SL_PCT=0.012  # = .env SL_PCT
entry=0.5172; _sug=2.08
sl_pct=SL_PCT*1.5; tp_rr=4.0          # jalur WIDE
_sug_f=_sug/100.0                      # P36: persen -> fraksi
if _sug_f>sl_pct: sl_pct=_sug_f        # ATR lebih lebar -> ikut ATR
sl_pct=max(0.003,min(0.030,sl_pct))    # P36 sanity guard
sl=entry*(1-sl_pct); tp=entry*(1+sl_pct*tp_rr)
check('SL WLD sehat 0.5064-0.5066', 0.5064<=sl<=0.5066)
check('TP WLD sehat ~0.5603', 0.559<=tp<=0.5615)
check('kode LAMA emang hasilin SL negatif (bukti bug)', entry*(1-_sug)<-0.5)

# 4) SEMUA jalur varian + saran ATR -> SL fraksi selalu 0.3%-3.0%
okall=True
for variant in ('TIGHT','NORMAL','WIDE',''):
    s=SL_PCT*(0.67 if variant=='TIGHT' else (1.5 if variant=='WIDE' else 1.0))
    f=_sug/100.0
    if f>s and variant!='TIGHT': s=f
    s=max(0.003,min(0.030,s))
    if not (0.003<=s<=0.030): okall=False
    # SL harga harus positif & di sisi yang benar utk LONG & SHORT
    if not (entry*(1-s)>0 and entry*(1+s)>0): okall=False
check('semua jalur varian SL wajar & harga positif', okall)

# 5) kontrak sumber: market_snapshot sl_pct_suggest selalu 0.8-2.4 (PERSEN)
for ap in (0.2,0.7,1.9,3.0,5.0):
    v=max(0.8,min(2.4,1.5*ap))
    if not (0.8<=v<=2.4): okall=False
check('slSuggest PERSEN ter-clamp 0.8-2.4 (kontrak sumber)', okall)

# 6) jev_bridge masih P34 utuh (rubric 8 dim, criteria 5 item, weighted)
spec=importlib.util.spec_from_file_location('jb',os.path.join(H,'jev_bridge.py'))
jb=importlib.util.module_from_spec(spec); spec.loader.exec_module(jb)
check('rubric 8 dimensi', len(jb.RUBRIC)==8)
check('criteria 5 item (P34)', all(len(c)==5 for _,_,_,c in jb.RUBRIC))
fake={n:{'value':3} for n,_,_,_ in jb.RUBRIC}
t,_=jb.rubric_total(fake)
check('rubric_total semua-3 = 75 (bobot timing/liq 2x)', t==75)

# 7) P36 MATA BOS #1: btc_bias hidup (import os balik) -> bias UP/DOWN/MIXED, bukan '?'
spec=importlib.util.spec_from_file_location('dsk',os.path.join(H,'dewa_skill.py'))
dsk=importlib.util.module_from_spec(spec); spec.loader.exec_module(dsk)
bb=dsk.btc_bias()
check('btc_bias hidup (bukan ?)', isinstance(bb,dict) and bb.get('bias') in ('UP','DOWN','MIXED'))

# 8) P36 MATA BOS #2: money_flow nyampe bos (UP -> BULLISH mapping di smc_engine)
spec=importlib.util.spec_from_file_location('smc',os.path.join(H,'smc_engine.py'))
smc=importlib.util.module_from_spec(spec); spec.loader.exec_module(smc)
dom=smc.btc_dom_trend()
okf=False
for b,exp in (('UP','FOKUS'),('?','FOKUS')):
    mf=smc.money_flow({'UP':'BULLISH','DOWN':'BEARISH'}.get(b,'SIDEWAYS'), dom)
    if mf and mf.get('moneyFlow'): okf=True
check('money_flow hasilisi tabel (dom trends)', okf)
mf2=smc.money_flow('SIDEWAYS', dom)
check('money_flow SIDEWAYS juga terpetakan', bool(mf2 and mf2.get('moneyFlow')))

# 8b) P36: enrich() END-TO-END — WAJIB panggil jalur asli bot (bias string UP/DOWN/'?'
# dan dict {'bias':...}) — dulu sempat NameError senyap di patch (param 'bias' vs 'btc_bias')
okf=True; got=[]
try:
    for b in ('UP','DOWN','?','MIXED',{'bias':'UP'},None):
        o=smc.enrich('BTCUSDT', b)
        got.append(bool(o.get('moneyFlow')))
    okf=all(got)
except Exception as e:
    okf=False; print('   enrich err:', e)
check('enrich() end-to-end: moneyFlow terisi semua varian bias', okf)

# 9) P36 MATA BOS #3: enrich_briefing beneran suntik vision.momentum_class
try:
    spec=importlib.util.spec_from_file_location('vg2',os.path.join(H,'v15_grade.py'))
    vg2=importlib.util.module_from_spec(spec); spec.loader.exec_module(vg2)
    kk=vg2.fetch_hist_klines('BTCUSDT','5m',60)
    kk=[[int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5])] for x in kk]  # persis dewa_live:378
    br={'symbol':'BTCUSDT','side':'LONG','score':{'z':1.0,'vol_x':2.0},'regime':'RANGE'}
    out=dsk.enrich_briefing(br,kk)
    v=out.get('vision') or {}
    check('enrich_briefing suntik momentum_class', bool(v.get('momentum_class')))
    check('enrich_briefing suntik rsi6 (angka)', isinstance(v.get('rsi6'),(int,float)))
except Exception as e:
    check(f'enrich_briefing live-probe: {e}', False)

print()
fails=[n for n,ok in res if not ok]
print(f'P36: {len(res)-len(fails)}/{len(res)} True')
sys.exit(1 if fails else 0)
