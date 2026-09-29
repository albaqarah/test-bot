#!/usr/bin/env python3
"""Skenario JELEK: harus REJECT + rubric rendah (KILL<50)."""
import json, os, sys
sys.path.insert(0,'/home/agentuser')
for l in open('/home/agentuser/.env'):
    l=l.strip()
    if '=' in l and not l.startswith('#'):
        k,v=l.split('=',1); os.environ.setdefault(k,v)
os.environ['JEV_API_KEY']=os.environ.get('JEV_API_KEY','')  # key dari env, JANGAN hardcode
import jev_bridge as jb
b={"symbol":"TESTUSDT","side":"LONG","grade":"A","source":"fade","regime":"RANGE","funding":-0.0002,
   "mss":"NONE","fvgStatus":"NONE","moneyFlow":"BEARISH+RISING",
   "score":{"z":2.1,"rsi":88.0,"vol_x":0.8,"imb":0.5},
   "vision":{"momentum_class":"kering","rsi6_now":86.0},
   "market":{"atr_pct":1.9,"vwap_z":2.3,"squeeze_on":False,"adx":14,"regime_strength":"CHOP",
     "mtf":{"5m":{"regime":"TREND_DOWN","rsi6":78,"dir":"DOWN"},"15m":{"regime":"TREND_DOWN","rsi6":70,"dir":"DOWN"},"1h":{"regime":"TREND_DOWN","rsi6":62,"dir":"DOWN"},"score":0},
     "divergence":{"bull_div":False,"bear_div":True},"vol_x_now":0.8,"dry_up":True,
     "session":"OFFHOURS","book_imb":-0.4,"oi_chg_pct":-2.0},
   "wickHint":{"dir":"SHORT","pattern":"shooting_star","strength":80,"climax":False,"atr_ok":True},
   "slSuggest":{"method":"ATR14x1.5","atr_pct":1.9,"sl_pct_suggest":2.4}}
out=jb.call_jev(b)
print("JELEK ->", out["decision"], "conf", out["confidence"], "rubric", out.get("rubric"),
      "noul", (out.get("rubric_detail") or {}).get("noul_risk"))
print("detail:", out.get("rubric_detail"))
