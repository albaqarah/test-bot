#!/usr/bin/env python3
"""P39 regression test — fix P30 cooldown bocor + done trim arbitrary.
Panggil fungsi ASLI dewa_live (lesson P36: test WAJIB jalur asli)."""
import sys, os, json, importlib
sys.path.insert(0,'/home/agentuser')
os.environ['JEV_API_KEY']='test-key-offline'  # offline, JANGAN sentuh API beneran

import dewa_live as dl
importlib.reload(dl)

ok=[]; fail=[]
def chk(name, cond, info=''):
    (ok if cond else fail).append(name)
    print(('PASS' if cond else 'FAIL'), name, info)

# --- 1) _p39_trim: trim by bar_ts terbaru, bukan urutan arbitrary ---
now_ts=1_700_000_000_000
done={(f'SYM{i:04d}USDT', now_ts+i*300000, 'L') for i in range(2500)}
newest_key=('NEWESTUSDT', now_ts+2499*300000, 'L')
done.add(newest_key)
out=dl._p39_trim(done, cap=2000)
chk('1. trim size == cap', len(out)==2000, f'({len(out)})')
chk('2. key TERBARU selamat', list(newest_key) in out)
chk('3. semua key lama terbuang itu yang paling tua',
    min(int(k[1]) for k in out)==now_ts+501*300000)  # 2501 key, drop 501 ter-kecil

# --- 4) bukti bug lama: list(set)[-600:] BISA buang key terbaru ---
import random
random.seed(7)
big={(f'P{i}', now_ts+random.randint(0,10**9), 'S') for i in range(2500)}
latest=('LATESTUSDT', now_ts+10**9+1, 'L'); big.add(latest)
old=list(big)[-600:]  # perilaku lama
new=dl._p39_trim(big)
chk('4a. perilaku LAMA bisa kehilangan key terbaru (bukti bug)', list(latest) not in old)
chk('4b. perilaku BARU selalu nyimpen key terbaru', list(latest) in new)

# --- 5) reject_cd ditulis SEBELUM save_state (urutan source) ---
src=open('/home/agentuser/dewa_live.py').read().split('\n')
w=sv=None
for i,l in enumerate(src):
    if "st.setdefault('reject_cd',{})[cd['sym']" in l: w=i
    if 'persist done-list + reject_cd (P39)' in l: sv=i
chk('5. urutan: tulis reject_cd SEBELUM save_state', w is not None and sv is not None and w<sv, f'(write@{w} save@{sv})')

# --- 6) jalur lama [list(k)[-600:]] udah musnah ---
chk('6. gak ada lagi baris kode lama list(done)[-600:]',
    not any(l.strip().startswith("st['done']=[list(k)") for l in src))

# --- 7-8) fungsi inti masih utuh (import asli = syntax & wiring sehat) ---
chk('7. _p38_dry_pass masih ada & kerja',
    dl._p38_dry_pass('kering', {'dir':'SHORT','strength':64})==False
    and dl._p38_dry_pass('kering', {'dir':'NONE','strength':64})==True)
chk('8. iterate & PAIRS tersedia', callable(dl.iterate) and len(dl.PAIRS)==41)

print()
print(f'P39: {len(ok)} PASS / {len(fail)} FAIL')
sys.exit(1 if fail else 0)
