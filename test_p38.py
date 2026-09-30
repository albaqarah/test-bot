#!/usr/bin/env python3
"""P38 regression test — WAJIB panggil jalur ASLI (lesson P36).
A: skip_dry recalibrasi (kasus NEAR 01:35 WIB: hint SHORT str 64 harus LOLOS)
B: framing fade baru (LENSA REVERSAL) + entryLoc masuk framing
C: entry_loc sensor (true/mid/chase) + injeksi enrich_market
D: argmax->total CONFIRMED (replay TRX: WIDE 0.31+NORMAL 0.29=0.60 vs REJECT 0.37)
+ rubric fence layer-2 tetap jalan, REJECT beneran tetap REJECT.
Offline: TIDAK menyentuh state/log prod, TIDAK memanggil API jev (mock _req)."""
import os, sys, json, importlib.util

# P35b ritual: import dewa_live DULU (loads .env OVERRIDE), baru module lain
sys.path.insert(0, '/home/agentuser')
import dewa_live as dl          # module asli bot
import jev_bridge as jb         # bos asli
import market_snapshot as ms    # sensor asli
import tg_notify as tg          # notif asli

R=[]  # (name, ok, detail)
def chk(name, ok, detail=''):
    R.append((name, ok, detail)); print(('PASS' if ok else 'FAIL'), name, ('| '+detail if detail else ''))

# ============ A: _p38_dry_pass (jalur asli dewa_live) ============
# kasus NEAR 30 Sep 01:35 WIB: kering + SHORT str 64 -> HARUS LOLOS (False = jangan skip)
chk('A1 NEAR-replay: kering+SHORT str64 LOLOS', dl._p38_dry_pass('kering', {'dir':'SHORT','strength':64}) == False)
chk('A2 kering+SHORT str54 tetap SKIP', dl._p38_dry_pass('kering', {'dir':'SHORT','strength':54}) == True)
chk('A3 kering+tanpa-dir tetap SKIP', dl._p38_dry_pass('kering', {'dir':'NONE','strength':90}) == True)
chk('A4 kering+tanpa-hint tetap SKIP', dl._p38_dry_pass('kering', {}) == True)
chk('A5 non-kering tak tersentuh gate', dl._p38_dry_pass('wick_extreme', {}) == False)
chk('A6 strength float 55.9 lolos', dl._p38_dry_pass('kering', {'dir':'LONG','strength':55.9}) == False)
chk('A7 strength string "64" lolos (cast aman)', dl._p38_dry_pass('kering', {'dir':'SHORT','strength':'64'}) == False)

# ============ B: framing fade ============
f=jb._framing({'side':'SHORT','source':'fade','vision':{}})
chk('B1 LENSA FADE ada', 'LENSA FADE' in f)
chk('B2 kontra-trend by design ada', 'KONTRA-TREND BY DESIGN' in f)
chk('B3 rs_trend guidance ada', 'rs_trend' in f)
f2=jb._framing({'side':'SHORT','source':'trend','vision':{}})
chk('B4 framing trend TIDAK berubah', 'TREND-PULLBACK' in f2 and 'LENSA FADE' not in f2)
# entryLoc ke framing (semua source)
f3=jb._framing({'side':'SHORT','source':'scalp','entryLoc':{'loc':'chase','swing_dist_atr':4.8,'swing_age_bars':15}})
chk('B5 entryLoc CHASE masuk framing', 'LOKASI ENTRY: chase (4.8 ATR' in f3)

# ============ C: entry_loc (jalur asli market_snapshot) ============
# sintetis: 40 bar, flat 100 lalu naik ke 104 di bar 20 (swing high), turun balik
kk=[]
for t in range(40):
    px=104.0 if t==20 else (100.0+min(t,20)*0.2-(0.2*max(0,t-20)) if t<=40 else 100.0)
    kk.append([1700000000000+t*300000, px, px+0.05, px-0.05, px, 1000.0])
el=ms.entry_loc(kk, i=38, side='SHORT')
chk('C1 SHORT dist>3 = chase', el['loc']=='chase', f"dist={el['swing_dist_atr']}")
# entry TEPAT di zona swing: ramp naik 100->104, puncak bar 20, turun tipis ke 103.5 (ATR tetap waras)
kk2=[]; _p=100.0
for t in range(40):
    if t>=10 and t<=20: _p=100.0+0.4*(t-10)
    elif t>20: _p=104.0-0.008*(t-20)   # turun tipis: dist ~1 ATR dari puncak
    kk2.append([1700000000000+t*300000, _p, _p+0.05, _p-0.05, _p, 1000.0])
el2=ms.entry_loc(kk2, i=38, side='SHORT')
chk('C2 SHORT deket swing high = true', el2['loc']=='true', f"dist={el2['swing_dist_atr']}, age={el2['swing_age_bars']}")
# LONG di lembah (harga terendah bar 38) -> true
kk3=[[b[0], b[1], b[2], b[3], (98.0 if j==38 else 102.0), 1000.0] for j,b in enumerate(kk)]
el3=ms.entry_loc(kk3, i=38, side='LONG')
chk('C3 LONG tepat lembah = true', el3['loc']=='true', f"dist={el3['swing_dist_atr']}")
# guard: i kecil / side salah -> None (never raise)
chk('C4 guard i<32 -> None', ms.entry_loc(kk, i=10, side='SHORT') is None)
chk('C5 guard side aneh -> None', ms.entry_loc(kk, i=38, side='MIDDLE') is None)
# injeksi via enrich_market asli (dgn kline sintetis, fetch gagal=field None tak bermasalah)
b={'symbol':'TESTUSDT','side':'SHORT'}
kk4=[[1700000000000+t*300000, 100.0, 100.5, 99.5, 100.0+t*0.01, 1000.0] for t in range(60)]
try:
    ms.enrich_market(b, 'TESTUSDT', kk4)
    chk('C6 enrich_market inject entryLoc', isinstance(b.get('entryLoc'), dict) and 'loc' in b.get('entryLoc',{}), str(b.get('entryLoc')))
except Exception as e:
    chk('C6 enrich_market inject entryLoc', False, repr(e))

# ============ D: argmax->total (call_jev asli, _req di-mock) ============
RUB={'rs_quality':{'value':3},'rs_timing':{'value':3},'rs_liquidity':{'value':3},
     'rs_trend':{'value':3},'rs_rr':{'value':3},'rs_crowd':{'value':3},
     'rs_vol':{'value':3},'rs_session':{'value':3}}
def mock_answers(probs, choice='REJECT', rub=3, noul=0.35):
    rubric={k:{'value':rub} for k in RUB}
    return {'decision':{'choice':choice,'probabilities':probs,'confidence':max(probs.values())},
            **rubric, 'noul_invalidate':{'noul':noul}, 'noul_flip':{'noul':noul}}

# TRX replay 29 Sep: WIDE .31 + NORMAL .29 + TIGHT .03 = .63 vs REJECT .37
trx=mock_answers({'CONFIRMED_WIDE':0.31,'CONFIRMED_NORMAL':0.29,'REJECT':0.37,'CONFIRMED_TIGHT':0.03})
jb._req=lambda p: {'answers':trx}
d=jb.call_jev({'symbol':'TRXUSDT','side':'SHORT','source':'fade'}, 'TRXUSDT')
chk('D1 TRX-replay: REJECT argmax -> CONFIRMED total', d['decision']=='CONFIRMED', f"conf={d.get('confidence')} var={d.get('variant')}")
chk('D2 conf = ΣCONFIRMED 63', d.get('confidence')==63, f"{d.get('confidence')}")
chk('D3 alasan P38-D tercatat', 'P38-D' in d.get('reason',''), d.get('reason','')[:80])
chk('D4 varian = p tertinggi (WIDE)', d.get('variant')=='WIDE')

# REJECT sah: ΣCONFIRMED 0.35 < 0.5
rej=mock_answers({'CONFIRMED_NORMAL':0.20,'CONFIRMED_WIDE':0.15,'REJECT':0.60})
jb._req=lambda p: {'answers':rej}
d2=jb.call_jev({'symbol':'XUSDT','side':'LONG','source':'fade'}, 'XUSDT')
chk('D5 REJECT sah tetap REJECT', d2['decision']=='REJECT')
# edge: ΣCONFIRMED 0.52 > REJECT 0.48 -> CONFIRMED
edge=mock_answers({'CONFIRMED_TIGHT':0.27,'CONFIRMED_NORMAL':0.25,'REJECT':0.48})
jb._req=lambda p: {'answers':edge}
d3=jb.call_jev({'symbol':'YUSDT','side':'LONG','source':'trend'}, 'YUSDT')
chk('D6 edge 0.52 vs 0.48 -> CONFIRMED', d3['decision']=='CONFIRMED', f"var={d3.get('variant')}")
# rubric KILL (layer-2) tetap menang meski ΣCONFIRMED besar
kill=mock_answers({'CONFIRMED_WIDE':0.40,'CONFIRMED_NORMAL':0.30,'REJECT':0.25}, rub=1)
jb._req=lambda p: {'answers':kill}
d4=jb.call_jev({'symbol':'ZUSDT','side':'LONG','source':'scalp'}, 'ZUSDT')
chk('D7 rubric KILL tetap REJECT (fence layer-2)', d4['decision']=='REJECT', d4.get('reason','')[:70])
# CONFIRMED argmax langsung: tak tersentuh D (jalan normal)
acc=mock_answers({'CONFIRMED_NORMAL':0.60,'REJECT':0.20}, choice='CONFIRMED_NORMAL')
jb._req=lambda p: {'answers':acc}
d5=jb.call_jev({'symbol':'WUSDT','side':'LONG','source':'fade'}, 'WUSDT')
chk('D8 argmax CONFIRMED normal jalan', d5['decision']=='CONFIRMED' and d5.get('variant')=='NORMAL')

# ============ NOTIF: baris Lokasi di fmt_open (jalur asli) ============
base={'symbol':'NEARUSDT','side':'SHORT','entry':5.155,'sl':5.248,'tp':5.0,'tp_rr':4.0,
      'conf':77,'reason':'test p38','regime':'TREND_DOWN','mclass':'wick_extreme','rsi6':34.3,
      'qty':3.879,'n_open':1,'saldo':-5.5,'grade':'A','variant':'WIDE'}
try:
    s1=tg.fmt_open({**base, 'entryLoc':{'loc':'true','swing_dist_atr':0.8,'swing_age_bars':0}})
    chk('N1 AT-TURN muncul di notif', '🎯 AT-TURN' in s1 and '0.8 ATR' in s1)
    s2=tg.fmt_open({**base, 'entryLoc':{'loc':'chase','swing_dist_atr':4.81,'swing_age_bars':15}})
    chk('N2 CHASE + warning di notif', '⚠️ CHASE' in s2 and '4.81 ATR' in s2)
    s3=tg.fmt_open(base)  # tanpa entryLoc -> tak crash, tanpa baris
    chk('N3 tanpa entryLoc aman', 'AT-TURN' not in s3 and 'CHASE' not in s3 and 'ENTRY' in s3)
except Exception as e:
    chk('N1-N3 fmt_open render', False, repr(e))

# ============ compile semua module inti ============
import py_compile
for f in ('dewa_live.py','jev_bridge.py','market_snapshot.py','dewa_skill.py','smc_engine.py',
          'hybrid_rules.py','tg_notify.py','tradfi_session.py','reversion_bot.py','v15_grade.py'):
    try:
        py_compile.compile('/home/agentuser/'+f, doraise=True)
        chk(f'compile {f}', True)
    except Exception as e:
        chk(f'compile {f}', False, str(e)[:80])

fails=[n for n,ok,_ in R if not ok]
print()
print(f"=== P38: {len(R)-len(fails)}/{len(R)} PASS ===")
if fails: print('FAIL:', fails); sys.exit(1)
