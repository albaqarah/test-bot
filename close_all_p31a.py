#!/usr/bin/env python3
"""Utility darurat: paksa-close semua posisi LIVE (market reduce-only) + bersihin SL/TP nyantol.
Pakai: python3 close_all_p31a.py"""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'.env')):
    l=l.strip()
    if l and not l.startswith('#') and '=' in l:
        k,v=l.split('=',1); os.environ.setdefault(k.strip(), v.strip())
import order_guard as og
import order_cleanup as oc
import tg_notify as tg

try:
    poss=og.open_positions()
    n=0
    for p in (poss or []):
        sym=p.get('symbol'); amt=float(p.get('positionAmt',0))
        if not sym or amt==0: continue
        close_side='SELL' if amt>0 else 'BUY'
        try:
            og._req('order', {'symbol':sym,'side':close_side,'type':'MARKET','quantity':abs(amt),
                              'reduceOnly':'true'})
            n+=1; print('closed', sym, amt)
        except Exception as e:
            print('close err', sym, e)
    print('total closed:', n)
except Exception as e:
    print('open_positions err:', e)

try:
    st=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'dewa_live_state.json')))
    syms=set(st.get('open',{}).keys())
except Exception:
    syms=set()
for sym in (syms or {'BTCUSDT'}):
    try:
        print(sym, oc.cleanup_leftovers(sym, live=True))
    except Exception as e:
        print('cleanup err', sym, e)
tg.send('🧹 close_all manual dijalankan — posisi dipaksa tutup + SL/TP nyantol dibersihkan')
