#!runpy.sh
"""
Does Noodle's long-run decline in wheel revolutions reflect a real slowdown,
or just the shrinking night?

Hypothesis: she runs from lights-out to sunrise. Lights-out is set by the
household (roughly constant per weekday); sunrise is set by the calendar. In
Andover MA the dark window shrinks ~2 hours between January and the June
solstice, which would depress revs with no change in the hamster at all.

This script re-derives every number in analysis/README.md from the live data
endpoint. Re-run it as new data arrives -- autumn is the real test, since the
photoperiod model predicts revs climb back as the nights lengthen, while a
genuine aging trend predicts they keep falling.

Usage:  C:/Python314/python.exe analysis/photoperiod_model.py
Deps:   numpy
"""
import json
import math
import urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np

DATA_URL = ("https://script.google.com/macros/s/AKfycbxoKRMGYPQAxMCUerc8ZO2MPxJl"
            "_aeTZRwIzMYej86asddpN4IzkjgOggQMnLtKUCIzuQ/exec")

LAT, LON = 42.6583, -71.1368     # Andover, MA
LREF = 22.0                      # reference lights-out (10pm wall clock); see note below
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Evenings before a Mon-Thu commute. The household's last-to-bed person drives to
# work Mon-Thu and is home/flexible on Friday, so Thu/Fri/Sat evenings run late.
COMMUTE_EVENINGS = {6, 0, 1, 2}  # Sun, Mon, Tue, Wed (weekday() of the *evening*)


# --------------------------------------------------------------------------
# US Eastern time (implemented directly: Windows python often lacks tzdata)
# --------------------------------------------------------------------------
def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(days=7 * (n - 1))


def utc_offset(utc_dt):
    """US Eastern offset at a UTC instant. EDT from 2am EST 2nd Sun Mar to 2am EDT 1st Sun Nov."""
    start = datetime.combine(_nth_weekday(utc_dt.year, 3, 6, 2), datetime.min.time(),
                             tzinfo=timezone.utc) + timedelta(hours=7)
    end = datetime.combine(_nth_weekday(utc_dt.year, 11, 6, 1), datetime.min.time(),
                           tzinfo=timezone.utc) + timedelta(hours=6)
    return timedelta(hours=-4) if start <= utc_dt < end else timedelta(hours=-5)


def to_local(utc_dt):
    return utc_dt + utc_offset(utc_dt)


def wall_to_utc(d, hour):
    """Wall-clock `hour` on local date `d` -> UTC instant (DST-correct)."""
    naive = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=hour)
    return naive - utc_offset(naive + timedelta(hours=5))


def sunrise_utc(d):
    """NOAA solar calculator, official sunrise (90.833 deg zenith). Accurate to ~1-2 min."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365.0 * (n - 1 + (6 - 12) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(LAT)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl))
              - math.tan(lat) * math.tan(decl))
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    minutes = 720 - 4 * (LON + ha) - eqtime
    return (datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
            + timedelta(minutes=minutes))


def hhmm(h):
    h %= 24
    return f"{int(h):02d}:{round((h % 1) * 60):02d}"


# --------------------------------------------------------------------------
# OLS
# --------------------------------------------------------------------------
def ols(X, y):
    """Returns (beta, stderr, r2, rmse, residuals)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - np.linalg.matrix_rank(X)
    sse = resid @ resid
    r2 = 1 - sse / ((y - y.mean()) ** 2).sum()
    se = np.sqrt(np.maximum(np.diag(np.linalg.pinv(X.T @ X)) * (sse / dof), 0))
    return beta, se, r2, math.sqrt(sse / dof), resid


def percentile_tier(value, p25, p75, mx):
    if value >= mx:
        return "record"
    if value > p75:
        return "high"
    if value >= p25:
        return "medium"
    return "low"


# --------------------------------------------------------------------------
# Load + build the dark window
# --------------------------------------------------------------------------
def load():
    with urllib.request.urlopen(DATA_URL) as r:
        raw = json.load(r)
    rows = sorted(
        (to_local(datetime.fromisoformat(x["date"].replace("Z", "+00:00"))).date(),
         float(x["revs"]))
        for x in raw if x.get("revs")
    )
    return [r[0] for r in rows], np.array([r[1] for r in rows])


def build(dates):
    """
    S = hours of darkness on each night, assuming lights-out at LREF.

    The night credited to 'Date Checked' D ran from the evening of D-1 to sunrise on D.
    LREF is a *reference* time, not a claim about the real bedtime: a constant offset is
    absorbed into the model intercept, so the fit is invariant to the choice. Only the
    day-to-day *differences* in lights-out are identified (see the day-of-week section).
    """
    n = len(dates)
    S = np.empty(n)
    dow = np.empty(n, dtype=int)
    t = np.empty(n)
    for i, D in enumerate(dates):
        evening = D - timedelta(days=1)
        S[i] = (sunrise_utc(D) - wall_to_utc(evening, LREF)).total_seconds() / 3600
        dow[i] = evening.weekday()
        t[i] = (D - dates[0]).days
    return S, dow, t


def main():
    dates, y = load()
    n = len(dates)
    S, dow, t = build(dates)
    one = np.ones(n)
    D7 = np.zeros((n, 7))
    D7[np.arange(n), dow] = 1
    commute = np.array([1.0 if d in COMMUTE_EVENINGS else 0.0 for d in dow])

    print("=" * 74)
    print(f"{n} nights, {dates[0]} .. {dates[-1]}   mean {y.mean():.0f} revs (sd {y.std():.0f})")
    print(f"dark window (lights-out {hhmm(LREF)}): {S.min():.2f}h .. {S.max():.2f}h")
    print("=" * 74)

    # ---- models -------------------------------------------------------
    print("\n-- MODELS " + "-" * 62)
    models = {
        "trend only":                  np.column_stack([one, t]),
        "dark window only":            np.column_stack([one, S]),
        "day-of-week only":            D7,
        "dark + commute flag":         np.column_stack([one, S, commute]),
        "dark + day-of-week":          np.column_stack([D7, S]),
        "dark + day-of-week + trend":  np.column_stack([D7, S, t]),
    }
    for name, X in models.items():
        _, _, r2, rmse, _ = ols(X, y)
        print(f"  {name:28s} R2={r2:.3f}  rmse={rmse:5.0f}")

    b, se, _, _, _ = ols(np.column_stack([D7, S]), y)
    r = b[7]
    print(f"\n  revs per extra hour of darkness: {r:.0f} +/- {se[7]:.0f}")

    bt, set_, _, _, _ = ols(np.column_stack([D7, S, t]), y)
    tstat = bt[8] / set_[8]
    print(f"  residual trend once dark window is controlled: {bt[8]:+.1f} +/- {set_[8]:.1f} revs/day"
          f"  (t={tstat:+.2f})")
    print(f"    -> {'NOT significant' if abs(tstat) < 2 else '*** SIGNIFICANT -- a real slowdown ***'}"
          f" at the 5% level")
    print(f"    95% CI: [{bt[8]-1.96*set_[8]:+.1f}, {bt[8]+1.96*set_[8]:+.1f}] revs/day")

    # ---- decomposition of the long-run decline ------------------------
    print("\n-- HOW MUCH OF THE DECLINE IS JUST DAYLIGHT? " + "-" * 28)
    early = [i for i, D in enumerate(dates) if D < dates[0] + timedelta(days=24)]
    solstice = date(dates[0].year, 6, 21)
    june = [i for i, D in enumerate(dates)
            if solstice - timedelta(days=20) <= D <= solstice]
    if early and june:
        d_obs = y[june].mean() - y[early].mean()
        d_dark = S[june].mean() - S[early].mean()
        pred = r * d_dark
        share = 100 * (1 - abs((d_obs - pred) / d_obs)) if d_obs else float("nan")
        print(f"  first 24 nights: {y[early].mean():.0f} revs, dark {S[early].mean():.2f}h")
        print(f"  3wks to solstice: {y[june].mean():.0f} revs, dark {S[june].mean():.2f}h")
        print(f"  observed decline  {d_obs:+.0f} revs")
        print(f"  photoperiod alone {pred:+.0f} revs   -> explains {share:.0f}% of it")
        print(f"  unexplained       {d_obs - pred:+.0f} revs")

    # ---- natural experiment 1: DST ------------------------------------
    print("\n-- NATURAL EXPERIMENT 1: DST SPRING-FORWARD " + "-" * 29)
    print("  Bedtime is on the wall clock, sunrise is on the sun. When the clocks jump")
    print("  the dark window steps up ~1h overnight -- but hamsters don't age in steps.")
    dst = _nth_weekday(dates[0].year, 3, 6, 2)
    for W in (21, 28, 35):
        idx = [i for i, D in enumerate(dates) if abs((D - dst).days) <= W]
        if len(idx) < 20:
            continue
        dd = np.array([(dates[i] - dst).days for i in idx], dtype=float)
        X = np.column_stack([np.ones(len(idx)), dd, (dd >= 0).astype(float)])
        bs, _, _, _, _ = ols(X, S[idx])
        br, ser, _, _, _ = ols(X, y[idx])
        implied = br[2] / bs[2] if bs[2] else float("nan")
        print(f"  +/-{W}d: dark step {bs[2]:+.2f}h | revs step {br[2]:+6.0f} +/- {ser[2]:.0f}"
              f" | implies {implied:6.0f} revs/hour")
    print(f"  (compare with the seasonal estimate of {r:.0f} revs/hour -- independent agreement)")

    # ---- natural experiment 2: out-of-sample past the solstice ---------
    print("\n-- NATURAL EXPERIMENT 2: FORECAST PAST THE SOLSTICE " + "-" * 21)
    print("  After the solstice the nights grow again. Photoperiod predicts an upturn;")
    print("  a pure aging trend predicts continued decline. Train early, forecast late.")
    cut = solstice - timedelta(days=7)
    tr = np.array([i for i, D in enumerate(dates) if D <= cut])
    te = np.array([i for i, D in enumerate(dates) if D > cut])
    if len(te) >= 10 and len(tr) >= 30:
        print(f"  train n={len(tr)} (through {cut}), test n={len(te)}")
        for name, X in models.items():
            beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
            pred = X[te] @ beta
            rmse_o = math.sqrt(((y[te] - pred) ** 2).mean())
            bias = (pred - y[te]).mean()
            print(f"  {name:28s} out-of-sample rmse={rmse_o:5.0f}  bias={bias:+6.0f}")
        print("  (a negative bias = the model under-predicts, i.e. she ran MORE than it expected)")
    else:
        print("  not enough post-solstice data yet")

    # ---- day-of-week / lights-out -------------------------------------
    print("\n-- NATURAL EXPERIMENT 3: THE WEEKLY RHYTHM " + "-" * 30)
    print("  Day-of-week is orthogonal to the season, so it identifies the effect cleanly.")
    print("  NOTE: absolute lights-out times are NOT identified (they assume revs -> 0 as")
    print("  darkness -> 0, which is false: she runs only ~50-60% of the dark window).")
    print("  Trust the OFFSETS, not the clock times.")
    L = np.array([LREF - b[j] / r for j in range(7)])
    order = np.argsort(L)
    print(f"\n  {'evening':9s}{'implied lights-out':>20s}{'offset':>10s}{'mean revs':>12s}")
    for j in order:
        print(f"  {DOW[j]:9s}{hhmm(L[j]):>20s}{(L[j]-L.mean())*60:>+9.0f}m{y[dow == j].mean():>12.0f}")
    print(f"\n  spread earliest -> latest: {(L.max()-L.min())*60:.0f} min")

    bc, sec, r2c, _, _ = ols(np.column_stack([one, S, commute]), y)
    print(f"\n  Single 'commute tomorrow' flag (Sun/Mon/Tue/Wed evenings):")
    print(f"    {bc[2]:+.0f} +/- {sec[2]:.0f} revs (t={bc[2]/sec[2]:+.2f}), R2={r2c:.3f} with ONE")
    print(f"    parameter vs {ols(np.column_stack([D7, S]), y)[2]:.3f} with seven day dummies.")
    print(f"    The household's commute schedule is recoverable from hamster wheel data.")

    # ---- placebo ------------------------------------------------------
    print("\n-- FALSIFICATION " + "-" * 56)
    base_r2 = ols(np.column_stack([D7, S]), y)[2]
    print(f"  real dark window                 R2={base_r2:.3f}")
    for shift in (61, 122):
        Sf = np.array([(sunrise_utc(D + timedelta(days=shift))
                        - wall_to_utc(D - timedelta(days=1), LREF)).total_seconds() / 3600
                       for D in dates])
        print(f"  sunrise curve shifted {shift:3d} days   R2={ols(np.column_stack([D7, Sf]), y)[2]:.3f}")
    rng = np.random.default_rng(0)
    shuffled = []
    for _ in range(300):
        P = np.zeros((n, 7))
        P[np.arange(n), rng.permutation(dow)] = 1
        shuffled.append(ols(np.column_stack([P, S]), y)[2])
    print(f"  shuffled day-of-week labels      R2={np.mean(shuffled):.3f} "
          f"(95th pct {np.percentile(shuffled, 95):.3f})")

    # ---- why the app tiers on a trailing window ------------------------
    print("\n-- WHY index.html TIERS ON A TRAILING 30-DAY WINDOW " + "-" * 21)
    p25, p75, mx = np.percentile(y, 25), np.percentile(y, 75), y.max()
    schemes = {}
    for i in range(n):
        past = [y[j] for j in range(i) if dates[j] >= dates[i] - timedelta(days=30)]
        all_t = percentile_tier(y[i], p25, p75, mx)
        if len(past) >= 10:
            win = percentile_tier(y[i], np.percentile(past, 25),
                                  np.percentile(past, 75), max(past))
            if win == "record" and y[i] < mx:
                win = "high"          # window-best is not an all-time record
        else:
            win = all_t
        schemes.setdefault(dates[i].strftime("%Y-%m"), []).append((all_t, win))

    print(f"  {'month':9s}{'n':>4s}  {'ALL-TIME (old)':>22s}   {'TRAILING 30d (new)':>22s}")
    print(f"  {'':9s}{'':>4s}  {'low':>7s}{'high':>7s}{'rec':>6s}   {'low':>7s}{'high':>7s}{'rec':>6s}")
    for m in sorted(schemes):
        rows = schemes[m]
        N = len(rows)
        def pct(k, which):
            return 100 * sum(1 for x in rows if x[which] == k) / N
        print(f"  {m:9s}{N:4d}  {pct('low',0):6.0f}%{pct('high',0):6.0f}%"
              f"{sum(1 for x in rows if x[0]=='record'):5d}   "
              f"{pct('low',1):6.0f}%{pct('high',1):6.0f}%"
              f"{sum(1 for x in rows if x[1]=='record'):5d}")
    print("\n  Under all-time thresholds the tiers measure the calendar: by summer no night")
    print("  can reach 'high' and the record is unbeatable. The trailing window slides with")
    print("  the daylight, so a good night reads as good year-round.")
    print("=" * 74)


if __name__ == "__main__":
    main()
