#!/usr/bin/env python3
"""Kalibrasi P34: 3 skenario (sempurna/sedang/jelek) lewat jev LIVE — gate 50/65 harus bermakna."""
import json, os, sys
sys.path.insert(0,'/home/agentuser')
for l in open('/home/agentuser/.env'):
    l=l.strip()
    if '=' in l and not l.startswith('#'):
        k,v=l.split('=',1); os.environ.setdefault(k,v)
os.environ['JEV_API_KEY']=os.environ.get('JEV_API_KEY','')  # key dari env, JANGAN hardcode
import jev_bridge as jb

def mk(kind):
    base={"symbol":"TESTUSDT","side":"LONG","grade":"A","source":"trend",
       "regime":"RANGE","funding":-0.0002,"mss":"MSS_BULLISH","fvgStatus":"ACTIVE [1.20, 1.24]",
       "moneyFlow":"BULLISH+FALLING","slSuggest":{"method":"ATR14x1.5","atr_pct":0.7,"sl_pct_suggest":1.05}}
    if kind=='sempurna':
        base.update({"score":{"z":-2.4,"rsi":12.0,"vol_x":2.6,"imb":-0.55},
            "vision":{"momentum_class":"climax","rsi6_now":11.5},
            "market":{"atr_pct":0.7,"vwap_z":-2.4,"squeeze_on":True,"adx":28,"regime_strength":"TREND",
              "mtf":{"5m":{"regime":"TREND_UP","rsi6":18,"dir":"UP"},"15m":{"regime":"TREND_UP","rsi6":32,"dir":"UP"},"1h":{"regime":"TREND_UP","rsi6":45,"dir":"UP"},"score":3},
              "divergence":{"bull_div":True,"bear_div":False},"vol_x_now":2.6,"dry_up":False,
              "session":"LONDON","book_imb":0.42,"bid_wall":500000,"ask_wall":90000,"oi_chg_pct":1.5},
            "wickHint":{"dir":"LONG","pattern":"hammer","strength":85,"climax":True,"atr_ok":True}})
    elif kind=='sedang':
        base.update({"score":{"z":-1.6,"rsi":28.0,"vol_x":1.3,"imb":-0.2},
            "vision":{"momentum_class":"normal","rsi6_now":27.0},
            "market":{"atr_pct":0.6,"vwap_z":-1.1,"squeeze_on":False,"adx":16,"regime_strength":"CHOP",
              "mtf":{"5m":{"regime":"RANGE","rsi6":35,"dir":"UP"},"15m":{"regime":"RANGE","rsi6":44,"dir":"DOWN"},"1h":{"regime":"RANGE","rsi6":52,"dir":"DOWN"},"score":1},
              "divergence":{"bull_div":False,"bear_div":False},"vol_x_now":1.3,"dry_up":False,
              "session":"ASIA","book_imb":0.05,"oi_chg_pct":0.1},
            "wickHint":{"dir":"LONG","pattern":"pin_down","strength":58,"climax":False,"atr_ok":True}})
    else:
        base.update({"score":{"z":2.1,"rsi":88.0,"vol_x":0.8,"imb":0.5},
            "vision":{"momentum_class":"kering","rsi6_now":86.0},
            "market":{"atr_pct":1.9,"vwap_z":2.3,"squeeze_on":False,"adx":14,"regime_strength":"CHOP",
              "mtf":{"5m":{"regime":"TREND_DOWN","rsi6":78,"dir":"DOWN"},"15m":{"regime":"TREND_DOWN","rsi6":70,"dir":"DOWN"},"1h":{"regime":"TREND_DOWN","rsi6":62,"dir":"DOWN"},"score":0},
              "divergence":{"bull_div":False,"bear_div":True},"vol_x_now":0.8,"dry_up":True,
              "session":"OFFHOURS","book_imb":-0.4,"oi_chg_pct":-2.0},
            "wickHint":{"dir":"SHORT","pattern":"shooting_star","strength":80,"climax":False,"atr_ok":True}})
    return base

for kind in ('sempurna','sedang','jelek'):
    out=jb.call_jev(mk(kind))
    print(f'--- {kind.upper():9s} -> {out["decision"]:8s} conf={out["confidence"]:3d} rubric={out.get("rubric")} noul_risk={ (out.get("rubric_detail") or {}).get("noul_risk") } variant={out.get("variant")}')
    print('    detail:', out.get('rubric_detail'))
