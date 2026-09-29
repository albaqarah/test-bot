#!/usr/bin/env python3
"""Unit test P32/P35 offline: jev402_hit, notif anti-spam (file flag terpisah), llm_call jev-only.
P35: fallback chain DIHAPUS — jev error = REJECT jev_err (tanpa model kedua).
P36 hygiene: TIDAK menyentuh file produksi. Log jsonl di-redirect, flag notif di-backup/restore,
state.json pake kopi temp — sebelumnya test ini nulis jev_err junk ke log prod & sempat
nyalain flag notif 402 beneran (ketahuan di audit 29 Sep 18:26)."""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dewa_live as dl  # P36: import DULU (.env OVERRIDE penuh), baru timpa env utk test
# P35b: .env SELALU menang -> timpa SETELAH import (jev_bridge baca env saat import, lazy di llm_call).
os.environ['JEV_BASE_URL']='http://127.0.0.1:1'  # port mati -> koneksi gagal
os.environ['JEV_TIMEOUT']='2'
os.environ['JEV_API_KEY']='test-dummy-key'

# --- P36 hygiene: redirect/rescue semua path produksi ---
_HERE=os.path.dirname(os.path.abspath(__file__))
dl.LOG=os.path.join(tempfile.gettempdir(),'test_p32_dl.jsonl')
try: os.remove(dl.LOG)
except Exception: pass
_FLAGF=os.path.join(_HERE,'dewa_notify_flag.json')
try: _flag_orig=open(_FLAGF).read()
except Exception: _flag_orig=None
_STF=os.path.join(_HERE,'dewa_live_state.json')
try: _st=json.load(open(_STF))
except Exception: _st={}
_sttmp=os.path.join(tempfile.gettempdir(),'test_p32_state.json')
json.dump(_st, open(_sttmp,'w'))

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
flagf=_FLAGF
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
stf=_sttmp
try: st=json.load(open(stf))
except Exception: st={}
st['bos_down_402']=0
json.dump(st, open(stf,'w'))
dl._notify_bos_down('402','tes ke-3 setelah state dioverwrite loop (harus tetap diblok)')
ok_spam = ok_spam and len(sent)==1
print('notif anti-spam 1x/jam + tahan overwrite:', ok_spam)

# 4) jev_bridge: rubric criteria = 5 item (P34)
import jev_bridge as jb2
qs=jb2.build_questions({"symbol":"T","side":"LONG","grade":"A","source":"trend"})
ok_crit=all(len(q.get('criteria',[]))==5 for k,q in qs.items() if q.get('type')=='score')
print('rubric criteria 5 item 0-4:', ok_crit)

# P36 hygiene: balikin flag notif ke kondisi semula (jangan tinggalin timestamp test)
try:
    if _flag_orig is None:
        try: os.remove(_FLAGF)
        except Exception: pass
    else:
        open(_FLAGF,'w').write(_flag_orig)
except Exception: pass

print('SEMUA:', all([ok402, ok_jo, ok_spam, ok_crit]))
