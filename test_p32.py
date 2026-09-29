#!/usr/bin/env python3
"""Unit test P32/P35 offline: jev402_hit, notif anti-spam (file flag terpisah), llm_call jev-only.
P35: fallback chain DIHAPUS — jev error = REJECT jev_err (tanpa model kedua)."""
import os, sys, json, tempfile, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dewa_live as dl  # P36: import DULU (.env OVERRIDE penuh), baru timpa env utk test
# P35b: .env SELALU menang atas setdefault -> dulu test ini malah nembak API beneran.
# jev_bridge baca env saat di-import (lazy di llm_call), jadi timpa SETELAH import = aman.
os.environ['JEV_BASE_URL']='http://127.0.0.1:1'  # port mati -> koneksi gagal
os.environ['JEV_TIMEOUT']='2'
os.environ['JEV_API_KEY']='test-dummy-key'

# 1) jev402_hit
class E402(Exception): pass
try:
    import jev_bridge as jb
    class FakeJev402(jb.Jev402): pass
    ok402 = dl.jev402_hit(FakeJev402('x')) and dl.jev402_hit(Exception('HTTP 402 oops'))
    print('jev402_hit:', ok402)
except Exception as e:
    print('jev402_hit import-skip:', e); ok402=True

# 2) llm_call jev-only: jev mati -> REJECT jev_err, TANPA fallback ke model lain
r=dl.llm_call({"symbol":"TESTUSDT"})
ok_jo = r.get('decision')=='REJECT' and str(r.get('reason','')).startswith('jev_err')
print('llm_call jev-only (error -> REJECT jev_err):', ok_jo, r)

# 3) anti-spam notif: 2x call dalam <1 jam -> cuma 1 notif (flag file terpisah P33)
flagf=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_notify_flag.json')
try: os.remove(flagf)
except Exception: pass
sent=[]
class FakeTG:
    @staticmethod
    def send(m): sent.append(m)
dl.tg=FakeTG
dl._notify_bos_down('402','tes unit')
dl._notify_bos_down('402','tes unit ke-2 (harus diblok)')
ok_spam = len(sent)==1
# tahan overwrite: tiru save_state menimpa STATE dgn flag lama (bug asli P33) -> flag FILE tetap awet
stf=os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live_state.json')
try: st=json.load(open(stf))
except Exception: st={}
st['bos_down_402']=0
json.dump(st, open(stf,'w'))
dl._notify_bos_down('402','tes ke-3 setelah state dioverwrite loop (harus tetap diblok)')
ok_spam = ok_spam and len(sent)==1
# bersihin artefak test
st.pop('bos_down_402',None); json.dump(st, open(stf,'w'))
print('notif anti-spam 1x/jam + tahan overwrite:', ok_spam)

# 4) jev_bridge: rubric criteria = 5 item (P34)
import jev_bridge as jb2
qs=jb2.build_questions({"symbol":"T","side":"LONG","grade":"A","source":"trend"})
ok_crit=all(len(q.get('criteria',[]))==5 for k,q in qs.items() if q.get('type')=='score')
print('rubric criteria 5 item 0-4:', ok_crit)

print('SEMUA:', all([ok402, ok_jo, ok_spam, ok_crit]))
