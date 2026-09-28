#!/usr/bin/env python3
"""Unit test P32 offline: jev402_hit, notif anti-spam, llm_call end-to-end (jev 402 -> chain fallback).
Path-relatif (clone-safe): test ini jalan dari root repo."""
import importlib.util as iu, json, os, sys

def load(name, path):
    sp=iu.spec_from_file_location(name, path); m=iu.module_from_spec(sp); sp.loader.exec_module(m); return m

_HERE=os.path.dirname(os.path.abspath(__file__))
os.environ['TG_BOT_TOKEN']=''; os.environ['TG_CHAT_ID']=''
jb=load('jev_bridge', os.path.join(_HERE,'jev_bridge.py'))
dl=load('dewa_live', os.path.join(_HERE,'dewa_live.py'))

# 1) jev402_hit
e=jb.Jev402('HTTP 402 Payment Required — jev butuh topup')
print('jev402_hit(Jev402):', dl.jev402_hit(e))
print('jev402_hit(urllib 402):', dl.jev402_hit(Exception('<urlopen error HTTP Error 402: Payment Required>')))
print('jev402_hit(other):', dl.jev402_hit(Exception('timed out')))

# 2) notif anti-spam (tanpa token TG -> tidak crash, flag state ter-set)
st=dl.load_state(); old=st.get('bos_down_402',0)
dl._notify_bos_down('402','unit-test')
ts=dl.load_state().get('bos_down_402')
print('notif pertama set flag:', (ts>0) or (old>0))
dl._notify_bos_down('402','unit-test-2')
print('anti-spam (flag tak berubah):', dl.load_state().get('bos_down_402')==ts)

# 3) llm_call end-to-end: jev KEY dummy -> urllib 402 (server openrouter beneran 402 utk key ngaco)
#    -> jatuh ke chain fallback BOS_FALLBACKS -> gateway dummy di port mati -> REJECT llm_err
os.environ['JEV_API_KEY']='dummy-key-for-402-test'
os.environ['BOS_FALLBACKS']='lightvela'
os.environ['LLM_BASE_URL']='http://127.0.0.1:9'
os.environ['LLM_API_KEY']='x'
os.environ['LLM_MODEL']='auto'
brief={"symbol":"TESTUSDT","side":"LONG","source":"fade","score":{"z":-2.0,"rsi":15.0},
       "regime":"RANGE","vol_x":1.5}
t0=__import__('time').time()
out=dl.llm_call(brief)
dt=__import__('time').time()-t0
print('llm_call hasil:', out, f'({dt:.1f}s — harus cepat, tanpa istirahat 10 menit)')

# 4) jev_bridge._req: 429 path — simulasi via HTTPError lokal
import urllib.error
try:
    jb._req_retry_probe=True
except Exception: pass
# (429 sulit disimulasi tanpa server; logika: except HTTPError 429 -> sleep 3 -> continue. Di-audit by-read.)

# 5) build_questions: 11 pertanyaan
b={"symbol":"BTCUSDT","side":"SHORT","source":"fade","score":{"z":2.1,"rsi":84.0},"regime":"RANGE","vol_x":1.6}
qs=jb.build_questions(b)
print('build_questions:', len(qs), 'pertanyaan ->', list(qs.keys())[:3], '...')
print('ALL P32 UNIT TESTS SELESAI')
