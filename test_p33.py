#!/usr/bin/env python3
"""Unit test P33: anti-spam notif (file terpisah) + persona fallback P32 (market/wickHint/slSuggest)."""
import json, os, importlib.util as iu

_HERE=os.path.dirname(os.path.abspath(__file__))
os.environ["TG_BOT_TOKEN"]=""; os.environ["TG_CHAT_ID"]=""

def load(name, path):
    sp=iu.spec_from_file_location(name, path); m=iu.module_from_spec(sp); sp.loader.exec_module(m); return m

dl=load("dewa_live", os.path.join(_HERE,"dewa_live.py"))
ds=load("dewa_skill", os.path.join(_HERE,"dewa_skill.py"))

# 1) persona fallback P32
ok_p = ("WICK-HUNTER" in ds.SYSTEM_PROMPT) and ("vwap_z" in ds.SYSTEM_PROMPT) and ("slSuggest" in ds.SYSTEM_PROMPT)
print("persona fallback P32:", ok_p, "| panjang prompt:", len(ds.SYSTEM_PROMPT))

# 2) anti-spam: flag di file TERPISAH, tahan overwrite state memori
ff=os.path.join(_HERE,"dewa_notify_flag.json")
if os.path.exists(ff): os.remove(ff)
dl._notify_bos_down("402","test-1")
f1=json.load(open(ff)).get("bos_down_402")
dl._notify_bos_down("402","test-2")   # harus skip (< 1 jam)
f2=json.load(open(ff)).get("bos_down_402")
print("flag anti-spam diset:", bool(f1), "| notif ke-2 diblok:", f1==f2)

# 3) state utama TIDAK dipakai utk flag
st=json.load(open(os.path.join(_HERE,"dewa_live_state.json")))
print("state utama tidak dimodifikasi notif:", "bos_down_402" not in st)

# 4) simulasi overwrite state oleh loop (penyebab spam lama) -> flag tetap awet
st["bos_down_402"]=0
json.dump(st, open(os.path.join(_HERE,"dewa_live_state.json"),"w"))
dl._notify_bos_down("402","test-3")
f3=json.load(open(ff)).get("bos_down_402")
print("tahan overwrite loop:", f3==f1)
print("P33 TEST SELESAI")
