#!/usr/bin/env python3
"""P14: TradFi session gate (CME hours) — bot entry logam HANYA saat session OPEN.
CME metals hours: Senin 06:00 ET - Sabtu 05:00 ET, daily break 17:00-18:00 ET (isinya settlement).
Implementasi pakai UTC: ET = UTC-4 (EDT) / UTC-5 (EST) — pakai konversi sederhana EDT (Mar-Nov) biar gak butuh tz db.
OPEN: Mon-Fri kecuali break harian 21:00-22:00 UTC (EDT), dan weekend CLOSED (dari Jumat 21:00 UTC sampai Senin 21:00 UTC... 
tepatnya: Fri 17:00 ET close -> Sun 18:00 ET open. EDT: Fri 21:00 UTC -> Sun 22:00 UTC.
PAXG dihitung ikut aturan yang sama sesuai permintaan user (walau token gold sebenarnya 24/7).
"""
from datetime import datetime, timezone

TRADFI={'XAUUSDT','XAGUSDT','XPTUSDT','PAXGUSDT'}

def _et_parts(ts=None):
    dt=datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(ts/1000, tz=timezone.utc)
    # EDT (UTC-4) Mar-Nov; EST (UTC-5) sisanya — approximation tanpa tz db
    off=4 if 3<=dt.month<=11 else 5
    from datetime import timedelta
    et=dt-timedelta(hours=off)
    return et.weekday(), et.hour, et  # day/hour dalam ET (benar di dekat midnight UTC)

def tradfi_open(ts=None):
    """True kalau CME metals session OPEN. Weekend CLOSED + daily break 17:00-18:00 ET."""
    day,h,dt=_et_parts(ts)
    # weekend: dari Jumat >=17:00 ET sampai Senin <18:00 ET... CME: close Fri 17:00, open Sun 18:00 ET
    if day==4 and h>=17: return False   # Jumat >= 17:00 ET (close weekend)
    if day==5: return False             # Sabtu
    if day==6 and h<18: return False    # Minggu < 18:00 ET (belum open)
    if h==17: return False              # daily break 17:00-18:00 ET
    return True

def tradfi_label(ts=None):
    day,h,dt=_et_parts(ts)
    st='OPEN' if tradfi_open(ts) else 'CLOSED'
    days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    why='WEEKEND' if day in (5,6) or (day==0 and h<18) else ('DAILY BREAK' if h==17 else '')
    return st, why, f"ET {days[day]} {h:02d}:{dt.minute:02d}"

if __name__=='__main__':
    print(tradfi_label())


# ==== P23: TRADFI FORCE-FLAT ZONE ====
# 3 jam sebelum break/close: kurir berhenti nyetor sinyal logam/PAXG (irit API bos + anti volume kopong)
# 2 jam sebelum close: posisi TradFi terbuka dipaksa cair (alasan tradfi_eod)
def tradfi_window(ts=None):
    """Return (entry_blocked, force_flat, label).
    entry_blocked = True mulai 14:00 ET (3 jam sebelum 17:00) / weekend zone
    force_flat    = True mulai 16:00 ET (2 jam sebelum 17:00) / weekend zone"""
    day,h,dt=_et_parts(ts)
    wknd_eb = (day==4 and h>=14) or day==5 or (day==6 and h<18)  # blok entry: Jumat>=14:00 .. Minggu 18:00
    wknd_ff = (day==4 and h>=16) or day==5 or (day==6 and h<18)  # force flat: Jumat>=16:00
    daily_break = (day not in (5,)) and h>=14 and h<18           # Sen-Jum 14:00-18:00 (termasuk break 17-18)
    ff = wknd_ff or ((day!=5) and h>=16 and h<18)
    eb = wknd_eb or daily_break
    return eb, ff, 'WEEKEND' if wknd_eb else ('DAILY BREAK' if daily_break else '')
