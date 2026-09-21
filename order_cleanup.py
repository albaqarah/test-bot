#!/usr/bin/env python3
"""
order_cleanup.py — Poin 4: setelah posisi close, pastikan TIDAK ada SL/TP nyantol.
Dry run : hapus SL/TP virtual dari state.
Live    : cancel semua openOrders closePosition symbol tsb via Binance API, lalu VERIFIKASI.
"""
import json, os

STATE='/home/agentuser/dewa_live_state.json'

def cleanup_leftovers(symbol, live=False):
    """Return dict status. Di live: cancel + verifikasi loop 3x."""
    # dry run: cukup pastikan ga ada entry virtual nyantol
    try:
        st=json.load(open(STATE))
    except Exception:
        return {'ok':True,'mode':'dry','note':'no state'}
    changed=False
    if symbol in st.get('open',{}):
        del st['open'][symbol]; changed=True
        json.dump(st, open(STATE,'w'), indent=1)
    if not live:
        return {'ok':True,'mode':'dry','removed_virtual':changed}
    # live: cancel openOrders symbol
    try:
        import order_guard as og
        oo=og._req('GET','/fapi/v1/openOrders',{'symbol':symbol})
        cancelled=0
        for o in oo:
            if o.get('closePosition') or o.get('type') in ('STOP_MARKET','TAKE_PROFIT_MARKET'):
                try:
                    og._req('DELETE','/fapi/v1/order',{'symbol':symbol,'orderId':o['orderId']})
                    cancelled+=1
                except Exception:
                    pass
        # verifikasi: harus kosong
        for _ in range(3):
            oo2=og._req('GET','/fapi/v1/openOrders',{'symbol':symbol})
            if not oo2: return {'ok':True,'mode':'live','cancelled':cancelled}
        return {'ok':False,'mode':'live','note':'leftover remain'}
    except Exception as e:
        return {'ok':False,'mode':'live','err':str(e)[:80]}

if __name__=='__main__':
    import sys
    print(cleanup_leftovers(sys.argv[1] if len(sys.argv)>1 else 'BTCUSDT'))
