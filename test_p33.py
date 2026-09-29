#!/usr/bin/env python3
"""Unit test P33/P35: anti-spam notif 402 (file flag terpisah) + kurir dewa_skill utuh.
P35: persona fallback (SYSTEM_PROMPT) DIHAPUS — full jev, jadi test memastikan TIDAK ADA lagi."""
import json, os, importlib.util as iu

_HERE=os.path.dirname(os.path.abspath(__file__))
os.environ["TG_BOT_TOKEN"]=""; os.environ["TG_CHAT_ID"]=""

def load(name, path):
    sp=iu.spec_from_file_location(name, path); m=iu.module_from_spec(sp); sp.loader.exec_module(m); return m

dl=load("dewa_live", os.path.join(_HERE,"dewa_live.py"))
ds=load("dewa_skill", os.path.join(_HERE,"dewa_skill.py"))

# 1) P35: SYSTEM_PROMPT fallback sudah TIDAK ADA
ok_no_persona = not hasattr(ds, "SYSTEM_PROMPT")
print("P35 persona fallback dihapus:", ok_no_persona)

# 2) kurir tetap utuh
ok_kurir = all(callable(getattr(ds, f, None)) for f in ("build_briefing","build_extras","enrich_briefing","classify_momentum"))
print("kurir dewa_skill utuh:", ok_kurir)

# 3) anti-spam: flag di file TERPISAH, tahan overwrite state memori
ff=os.path.join(_HERE,"dewa_notify_flag.json")
if os.path.exists(ff): os.remove(ff)
sent=[]
class FakeTG:
    @staticmethod
    def send(m): sent.append(m)
dl.tg=FakeTG
dl._notify_bos_down("402","test-1")
f1=json.load(open(ff)).get("bos_down_402")
dl._notify_bos_down("402","test-2")   # harus skip (< 1 jam)
f2=json.load(open(ff)).get("bos_down_402")
print("flag anti-spam diset:", bool(f1), "| notif ke-2 diblok:", f1==f2, "| terkirim:", len(sent)==1)

# 4) notif 402 GAK nyebut fallback/lightvela lagi
if sent:
    txt=sent[0].lower()
    print("notif tanpa 'fallback/lightvela':", ('fallback' not in txt and 'lightvela' not in txt))

# 5) state utama TIDAK dipakai utk flag
st=json.load(open(os.path.join(_HERE,"dewa_live_state.json")))
print("state utama tidak dimodifikasi notif:", "bos_down_402" not in st)

# 6) simulasi overwrite state oleh loop (penyebab spam lama) -> flag tetap awet
st["bos_down_402"]=0
json.dump(st, open(os.path.join(_HERE,"dewa_live_state.json"),"w"))
dl._notify_bos_down("402","test-3")
f3=json.load(open(ff)).get("bos_down_402")
print("tahan overwrite loop:", f3==f1)
print("P33/P35 TEST SELESAI")
