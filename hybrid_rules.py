#!/usr/bin/env python3
"""
hybrid_rules.py — KURIR ENGINE PROTOCOL v7.0 (STRICT MATHEMATICAL FILTER)
Rombak total 30 Sep 2026 (ACC user "Pokoknya gw mau rombak total... Titik!"):
- 3 engine preset: FADE CLIMAX / SCALP HIGH-MOMENTUM / TREND PULLBACK
- HIGHER TF FILTER (Anti-Trap): WAJIB EMA20 vs EMA50 (15m) + struktur 1h
- P6-loose & scalp momentum-turn (era v6.7) DIHAPUS — sumber 16/23 sinyal RSI netral
- wick 0.15 (era lama) dibuang; fade pakai wick>=40% sesuai spec v7.0
Semua kandidat tetap lolos bos jev (persona v7.0) sebelum entry.
"""
import reversion_bot as rb
import os


def ema_series(vals, n):
    k = 2 / (n + 1); out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def build_htf_maps(sym, k5_len):
    """EMA20+EMA50 dari 15m & struktur 1h + vol_x_1h, dipetakan ke timeline 5m.
    Return {'15m': {ts: (ema20, ema50)}, '1h': {ts: (ema20, ema50, volx)}, '1h_struct': str}.
    CATATAN: ts = OPEN time bar (ms). Lookup 5m->15m WAJIB forward-fill (align_htf),
    karena ts 5m cuma match 1/3 dgn ts 15m (pecahan 15 menit)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'vg', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v15_grade.py'))
    vg = importlib.util.module_from_spec(spec); spec.loader.exec_module(vg)
    maps = {'15m': {}, '1h': {}, '1h_struct': 'RANGING'}
    kh1h = None
    for tf in ('15m', '1h'):
        cnt = 1000 if tf == '15m' else 500
        try:
            kh = vg.fetch_hist_klines(sym, tf, cnt)
            if tf == '1h': kh1h = kh
            c = [float(x[4]) for x in kh]
            e20, e50 = ema_series(c, 20), ema_series(c, 50)
            if tf == '15m':
                maps[tf] = {int(x[0]): (e20[j], e50[j]) for j, x in enumerate(kh)}
                maps['c15'] = [float(x[4]) for x in kh]  # v12.2: closes 15m utk sensor GMV2 (tanpa fetch ekstra)
            else:
                v = [float(x[5]) for x in kh]
                out = {}
                for j, x in enumerate(kh):
                    vma = (sum(v[j-20:j]) / 20) if j >= 20 and sum(v[j-20:j]) else None
                    volx = round(v[j] / vma, 2) if vma else None
                    out[int(x[0])] = (e20[j], e50[j], volx)
                maps[tf] = out
        except Exception:
            maps[tf] = {}
    # struktur 1h: trend kontinu / ranging / ekstrem (dump panik / pump euforia)
    try:
        kh = kh1h or vg.fetch_hist_klines(sym, '1h', 60)
        o = [float(x[1]) for x in kh]; c = [float(x[4]) for x in kh]
        e20 = ema_series(c, 20); e50 = ema_series(c, 50)
        if c[-1] > e20[-1] > e50[-1]: maps['1h_struct'] = 'BULLISH_CONTINUATION'
        elif c[-1] < e20[-1] < e50[-1]: maps['1h_struct'] = 'BEARISH_CONTINUATION'
        # ekstrem: 3 candle 1h terakhir body besar searah (>60% range masing2) + lari jauh dari EMA20
        def _runs(dirc):
            n = 0
            for j in range(len(kh) - 3, len(kh)):
                rng = kh[j][2] - kh[j][3]
                if rng <= 0: continue
                body = (c[j] - o[j]) / rng
                if (dirc > 0 and body > 0.6) or (dirc < 0 and body < -0.6): n += 1
            return n == 3
        if _runs(-1) and c[-1] < e20[-1] * 0.995: maps['1h_struct'] = 'BEARISH_EXTREME_DUMP'
        elif _runs(1) and c[-1] > e20[-1] * 1.005: maps['1h_struct'] = 'BULLISH_EXTREME_PUMP'
    except Exception:
        pass
    return maps


def align_htf(kts, m):
    """Forward-fill map HTF ke timeline 5m: utk tiap 5m ts ambil nilai bar HTF terakhir
    dgn open-ts <= kts. kts & keys(m) harus urut naik. Return list(len(kts)) nilai/None."""
    keys = sorted(m.keys())
    out = []; j = -1; best = None
    for t in kts:
        while j + 1 < len(keys) and keys[j + 1] <= t:
            j += 1; best = m[keys[j]]
        out.append(best)
    return out


def gen_fade_climax(kk, rs, zz, vsma):
    """ENGINE 1 — FADE CLIMAX (grade A sinyal konter pucuk/lembah):
    LONG  : RSI6 < 20 AND z < -1.5 AND wick bawah >= 40% range
    SHORT : RSI6 > 80 AND z > +1.5 AND wick atas >= 40% range
    Grade A = tambahan vol climax (vol_x > 1.5)."""
    sigs = []
    o = [r[1] for r in kk]; h = [r[2] for r in kk]; l = [r[3] for r in kk]
    c = [r[4] for r in kk]; v = [r[5] for r in kk]
    for i in range(210, len(c) - 2):
        r = rs[i]; z = zz[i]
        if r is None or z is None: continue
        rng = h[i] - l[i]
        if rng <= 0: continue
        wick_lo = (min(o[i], c[i]) - l[i]) / rng
        wick_hi = (h[i] - max(o[i], c[i])) / rng
        volx = v[i] / vsma[i] if vsma[i] else 1
        if r < 20 and z < -1.5 and wick_lo >= 0.40:
            sigs.append((i, 'L', 'A' if volx > 1.5 else 'B'))
        elif r > 80 and z > 1.5 and wick_hi >= 0.40:
            sigs.append((i, 'S', 'A' if volx > 1.5 else 'B'))
    return sigs


def gen_scalp_momentum(kk, rs, vsma):
    """ENGINE 2 — SCALP HIGH-MOMENTUM (agresif di pasar aktif):
    Trigger tunggal: vol_x >= 1.2 (v7.1 — dilonggarkan dr 1.5; grade A scalp
    tetap vol_x >= 2.0). Filter body>60% v7.0 DIHAPUS — kualitas struktur body
    dinilai bos via data kontrak JSON, bukan dicegat di kurir.
    Guard P12: BLOKIR LONG jika RSI6 > 85; BLOKIR SHORT jika RSI6 < 15."""
    sigs = []
    o = [r[1] for r in kk]; h = [r[2] for r in kk]; l = [r[3] for r in kk]
    c = [r[4] for r in kk]; v = [r[5] for r in kk]
    for i in range(210, len(c) - 2):
        rng = h[i] - l[i]
        if rng <= 0: continue
        volx = v[i] / vsma[i] if vsma[i] else 0
        x6 = rs[i]
        # v9.0: gate volx dilonggarkan ke >= 1.0 saat RSI6 di lembah (<25) / pucuk (>75)
        # (sesi tenang pun boleh setor; kualitas tetap dinilai bos)
        _gate = 1.0 if (x6 is not None and (x6 < 25 or x6 > 75)) else 1.2
        if volx < _gate: continue
        if c[i] > o[i]:
            if x6 is not None and x6 <= 85:   # P12 anti-pucuk
                sigs.append((i, 'L', 'A' if volx >= 2.0 else 'B'))
        elif c[i] < o[i]:
            if x6 is not None and x6 >= 15:   # P12 mirror anti-lembah
                sigs.append((i, 'S', 'A' if volx >= 2.0 else 'B'))
    return sigs


def gen_trend_pullback(kk, rs, vsma, htf15):
    """ENGINE 3 — TREND PULLBACK (ikut arus institusi):
    Harga 5m retrace menyentuh EMA20(15m) lalu pantul searah tren dgn vol_x > 1.0.
    Arah wajib searah cross EMA20/EMA50 (15m)."""
    sigs = []
    o = [r[1] for r in kk]; h = [r[2] for r in kk]; l = [r[3] for r in kk]
    c = [r[4] for r in kk]; v = [r[5] for r in kk]
    for i in range(210, len(c) - 2):
        m = htf15[i] if i < len(htf15) else None
        if m is None: continue
        e20, e50 = m[0], m[1]  # tuple (ema20, ema50[, volx]) hasil align_htf
        rng = h[i] - l[i]
        if rng <= 0: continue
        volx = v[i] / vsma[i] if vsma[i] else 0
        # BULLISH: EMA20 > EMA50, harga sentuh EMA20, close pantul naik
        if e20 > e50:
            touch = l[i] <= e20 * 1.001
            bounce = c[i] > o[i] and c[i] > e20
            if touch and bounce and volx > 1.0:
                sigs.append((i, 'L', 'A' if volx > 1.5 else 'B'))
        # BEARISH: EMA20 < EMA50, harga sentuh EMA20, close pantul turun
        elif e20 < e50:
            touch = h[i] >= e20 * 0.999
            bounce = c[i] < o[i] and c[i] < e20
            if touch and bounce and volx > 1.0:
                sigs.append((i, 'S', 'A' if volx > 1.5 else 'B'))
    return sigs


def gen_hybrid(kk, rs, zz, vsma, htf15, htf1h_struct, cek_1h=True, btcv=None):
    """KURIR v7.0: 3 engine + HIGHER TF FILTER (Anti-Trap).
    v9.0: EMA-cross 15m TIDAK lagi menyaring (v8.0); veto 1h BEARISH/BULLISH_EXTREME berlaku
    ke SEMUA engine (fade ikut sejak v9.0); data HTF hilang = fail-closed semua engine.
    htf15: list per-bar 15m (hasil align_htf, forward-fill) atau None; htf1h_struct: string struktur 1h
    (cek 1h dari cek_1h, default True). Output: (idx, side, grade, src); src in ('fade','scalp','trend').
    v9.0: btcv = Super Money Flow (rasio vol 3-bar BTC/SMA20, dari dewa_live) — lonjakan >= 1.5
    saat RSI6 kandidat di lembah (<25) / pucuk (>75) = suntikan volume raksasa -> grade A.
    v9.0: fade TIDAK lagi dikecualikan dari data-check HTF (fail-closed semua engine); veto 1h
    *_EXTREME berlaku ke semua; EMA-cross 15m tetap dicabut (v8.0).
    v11.0: PRE-EMPTIVE PEAK — fade murni SHORT RSI6>=88 / LONG RSI6<=12 + volx>=1.5 + ekor
    lawan>=35% => bypass data-check HTF & veto 1h + grade 'A+' (entri sebelum candle close)."""
    fade = [(s[0], s[1], s[2], 'fade') for s in gen_fade_climax(kk, rs, zz, vsma)]
    scalp = [(s[0], s[1], s[2], 'scalp') for s in gen_scalp_momentum(kk, rs, vsma)]
    trend = [(s[0], s[1], s[2], 'trend') for s in gen_trend_pullback(kk, rs, vsma, htf15)]
    allsigs = fade + scalp + trend
    # ============ HIGHER TF FILTER (Anti-Trap, WAJIB) ============
    # htf15 = list hasil align_htf (forward-filled): nilai 15m terakhir per bar 5m.
    # Data HTF hilang (None) = FAIL-CLOSED utk scalp/trend (mandat user: DILARANG
    # produksi sinyal tanpa validasi HTF); fade climax dikecualikan by design.
    by_bar = {}
    for s in allsigs:
        i, side, grade, src = s
        # v9.0 SUPER MONEY FLOW injection: lonjakan volume BTC searah (btcv >= 1.5) saat
        # RSI6 kandidat di lembah (<25) / pucuk (>75) = suntikan dana bandar -> grade A.
        r6 = rs[i]
        _extreme = r6 is not None and ((side == 'L' and r6 < 25) or (side == 'S' and r6 > 75))
        if _extreme and btcv is not None and btcv >= 1.5:
            grade = 'A'
        # ==== v11.0 PRE-EMPTIVE PEAK DETECTOR (directive) ====
        # Fade murni di pucuk/lembah ABSOLUT (SHORT RSI6>=88 / LONG RSI6<=12) + volx>=1.5 +
        # ekor lawan >=35% = jalur kilat: BYPASS data-check HTF & veto 1h (dilarang nunggu
        # close candle 5m), grade dipaksa 'A+' -> enforcer override CONFIRMED TIGHT.
        _volx = kk[i][5]/vsma[i] if vsma[i] else 0
        _o=[x[1] for x in kk]; _h=[x[2] for x in kk]; _l=[x[3] for x in kk]; _c=[x[4] for x in kk]
        _rng=_h[i]-_l[i]
        _wick_top=(_h[i]-max(_o[i],_c[i]))/_rng*100 if _rng>0 else 0.0
        _wick_bot=(min(_o[i],_c[i])-_l[i])/_rng*100 if _rng>0 else 0.0
        _preemptive=False
        if src=='fade' and r6 is not None:
            if side=='S' and r6>=88 and _volx>=1.5 and _wick_top>=35.0: _preemptive=True
            if side=='L' and r6<=12 and _volx>=1.5 and _wick_bot>=35.0: _preemptive=True
        if _preemptive:
            grade='A+'
        ok = True
        # v11.0: jalur pre-emptive bypass filter HTF (jalur kilat pucuk absolut); engine lain
        # tetap fail-closed None + veto 1h (v9.0). EMA-cross 15m tetap dicabut (v8.0).
        if not _preemptive:
            m = htf15[i] if i < len(htf15) else None
            if m is None:
                ok = False              # fail-closed: gak bisa validasi = gak boleh tembak
            if cek_1h:
                st = str(htf1h_struct)
                if side == 'L' and 'BEARISH_EXTREME' in st: ok = False
                if side == 'S' and 'BULLISH_EXTREME' in st: ok = False
        if not ok: continue
        by_bar.setdefault(i, []).append((side, grade, src))
    out = []
    for i in sorted(by_bar):
        ss = by_bar[i]
        sides = {s[0] for s in ss}
        if len(sides) > 1:
            # v7.1: konflik antar-engine di bar sama (fade LONG vs scalp SHORT di bar
            # washout, RSI6 15-20) — FADE MENANG, sinyal JANGAN dibuang (patch v7.1:
            # bos yang menilai, kurir gak boleh bikin sinyal sepi). Fade = engine
            # climax di bar itu; scalp cuma momentum searah wick.
            ss = [s for s in ss if s[2] == 'fade'] or ss
            sides = {s[0] for s in ss}
            if len(sides) > 1: continue        # tetap bentrok (tak mungkin) = kabut
        # v11.0: A+ (pre-emptive peak) TIDAK boleh ditimpa resolusi biasa.
        if any(s[1] == 'A+' for s in ss):
            grade = 'A+'
        else:
            grade = 'A' if (len(ss) > 1 or any(s[1] == 'A' for s in ss)) else 'B'
        out.append((i, ss[0][0], grade, ss[0][2]))
    return out


def fresh_recheck(cd, k_cache, rb, px=None):
    """v12.3 FRESH RE-CHECK — evaluasi ulang sinyal di DATA LIVE sebelum nanya bos.
    Latar: audit 2 Okt — bar sinyal bisa basi hingga 6 menit saat keputusan diambil
    (kasus 11:26 WIB: RSI6 bar sinyal 58.8, bar closed berikutnya 82.0 = pucuk
    tersembunyi; BCH A+ nembak pas RSI live udah 61 setelah pucuk 93).
    Input: cd kandidat (side masih 'L'/'S' — normalisasi ke LONG/SHORT terjadi belakangan),
    k_cache[sym] = klines 5m mentah 600 bar (bar terakhir = filler live), rb = reversion_bot
    (rsi6 Wilder), px = harga live ticker (boleh None).
    Return {'ok','why','rsi_now','k_now','demote','demote_why'}.
    - P12-LIVE (reinforcement rule lama, bukan gate baru): LONG dilarang RSI6 live > 85,
      SHORT dilarang RSI6 live < 15 — diukur ulang di tick live, bukan bar sinyal.
    - A+ STALENESS: jalur pre-emptive v11.0 dicabut kalau pucuk/lembah absolutnya udah
      basi di tick live (SHORT: RSI6 live < 80; LONG: RSI6 live > 20).
    - FADE-DEMOTE (kualifikasi fade No.4, bukan gate): sinyal fade (bukan pre-emptive)
      dgn climax-nya ilang di bar live — ekor searah sinyal < 25% (harga masih nge-push
      tanpa sumbu jenuh) — demote ke B, bos tetap ditanya (bukan REJECT paksa)."""
    out = {'ok': True, 'why': '', 'rsi_now': None, 'k_now': None, 'demote': False, 'demote_why': ''}
    try:
        sym = cd.get('sym'); s = cd.get('side')
        is_long = s in ('L', 'LONG')
        k5 = k_cache.get(sym) or []
        if len(k5) < 30:
            out['why'] = 'data kurang, fail-open'
            return out
        c = [float(x[4]) for x in k5[:-1]]          # bar closed (buang filler)
        if px is not None:
            try: c = c + [float(px)]                 # tick live
            except Exception: pass
        r6 = rb.rsi6(c)[-1]
        out['rsi_now'] = round(r6, 1) if r6 is not None else None
        lk = k5[-1]                                  # bar live: ekor searah sinyal sekarang
        _o, _h, _l, _c2 = float(lk[1]), float(lk[2]), float(lk[3]), float(lk[4])
        _rng = _h - _l
        _wt = (_h - max(_o, _c2)) / _rng * 100 if _rng > 0 else 0.0
        _wb = (min(_o, _c2) - _l) / _rng * 100 if _rng > 0 else 0.0
        out['k_now'] = round(_wb if is_long else _wt, 1)
        # 1) P12-LIVE
        if is_long and r6 is not None and r6 > 85:
            out['ok'] = False; out['why'] = f'P12-LIVE: RSI6 live {r6:.1f} > 85 — LONG dilarang (pucuk tersembunyi setelah bar sinyal)'
        elif (not is_long) and r6 is not None and r6 < 15:
            out['ok'] = False; out['why'] = f'P12-LIVE: RSI6 live {r6:.1f} < 15 — SHORT dilarang (lembah tersembunyi setelah bar sinyal)'
        # 2) A+ STALENESS (pucuk/lembah absolut udah basi)
        elif cd.get('grade') == 'A+' and r6 is not None:
            if is_long and r6 > 20:
                out['ok'] = False; out['why'] = f'A+ BASI: lembah absolut udah hilang (RSI6 live {r6:.1f} > 20, trigger bar sinyal <= 12)'
            elif (not is_long) and r6 < 80:
                out['ok'] = False; out['why'] = f'A+ BASI: pucuk absolut udah hilang (RSI6 live {r6:.1f} < 80, trigger bar sinyal >= 88)'
        # 3) FADE-DEMOTE: climax hilang di bar live (ekor searah sinyal < 25%)
        elif cd.get('src') == 'fade' and cd.get('grade') != 'A+':
            _tail = _wb if is_long else _wt
            if _tail < 25.0:
                out['demote'] = True
                out['demote_why'] = f'climax hilang: ekor {"bawah" if is_long else "atas"} bar live {(_tail):.0f}% < 25% (harga masih nge-push tanpa sumbu jenuh)'
    except Exception:
        out = {'ok': True, 'why': 'recheck err fail-open', 'rsi_now': None, 'k_now': None, 'demote': False, 'demote_why': ''}
    return out
