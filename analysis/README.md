# Is Noodle slowing down?

**Short answer: probably not.** The long-run decline in revolutions per night is
almost entirely explained by the shrinking dark window between lights-out and
sunrise. Once you control for it, the residual "she's getting slower" trend is
not statistically significant.

Run `photoperiod_model.py` to re-derive every number below from the live data
endpoint. All figures here are from the 173 nights of **2026-01-22 → 2026-07-13**;
re-run the script for current numbers.

```
C:/Python314/python.exe analysis/photoperiod_model.py     # needs numpy
```

## The hypothesis

Noodle is nocturnal. She starts running when the lights go out and stops around
sunrise. Lights-out is set by the household — roughly constant for a given weekday.
Sunrise is set by the calendar. In Andover MA (42.66°N) the dark window runs about
**9.1 hours in January but only 7.1 hours at the June solstice**.

At roughly **4,500 revolutions per hour of darkness**, that 2-hour loss costs about
9,000 revs a night — for no reason other than the tilt of the Earth.

## What the model finds

| Model | R² | RMSE (revs) |
|---|---|---|
| Long-run trend only | 0.375 | 4,109 |
| Dark window only | 0.397 | 4,034 |
| Day-of-week only | 0.153 | 4,854 |
| Dark window + commute flag | 0.509 | 3,650 |
| **Dark window + day-of-week** | **0.545** | **3,566** |
| Dark window + day-of-week + trend | 0.550 | 3,558 |

Two numbers carry the argument:

- **Photoperiod explains ~85% of the decline.** Observed drop from January to the
  solstice: −9,722 revs. Predicted from the shrinking dark window alone: −8,284.
- **The residual trend is not significant.** After controlling for the dark window:
  **−21 ± 16 revs/day** (t = −1.33, 95% CI [−53, +10]). Consistent with zero.

## Why this isn't just spurious correlation

The dark window and the passage of time both fall monotonically from January to
June, so they're badly confounded — which is exactly why a bare trend line also
scores a respectable R² = 0.375. Three places where the two hypotheses make
*different* predictions:

### 1. The daylight-saving discontinuity (8 March)

Bedtime is on the wall clock; sunrise is on the sun. When the clocks spring forward,
lights-out effectively moves an hour earlier *relative to the sun*, and the dark
window steps up ~1 hour **overnight**. Hamsters do not age in steps.

| Window | Dark step | Revs step | Implied revs/hour |
|---|---|---|---|
| ±21d | +0.81h | +2,561 ± 2,574 | 3,145 |
| ±28d | +0.85h | +3,991 ± 2,150 | 4,691 |
| ±35d | +0.87h | +4,693 ± 1,890 | 5,425 |

These bracket the seasonal estimate of **4,482 revs/hour** — an independent
replication from a clock change rather than from the calendar.

### 2. The solstice reversal (out-of-sample)

After 21 June the nights start growing again. Photoperiod predicts an upturn; a
pure aging trend predicts continued decline. Training only on data through 14 June
and forecasting the remaining 29 nights:

| Model | Out-of-sample RMSE | Bias |
|---|---|---|
| Trend only | 3,799 | **−1,290** |
| Dark window + day-of-week | **2,951** | +489 |

The trend model keeps marching downward and **under-predicts by ~1,300 revs/night**.
The photoperiod model is close to unbiased.

### 3. The weekly rhythm

Day-of-week is orthogonal to the season, so it identifies the effect cleanly.
Shuffling the day labels 300× yields R² = 0.42 (95th pct 0.44) against the real 0.545.

## The household's commute schedule, recovered from a hamster wheel

Sorting the evenings by implied lights-out produces this — indexed by *the evening
the lights went out*:

| Evening | Offset vs weekly mean | Mean revs |
|---|---|---|
| Sun | **−39 min** (earliest) | 22,947 |
| Wed | −27 min | 22,173 |
| Tue | −19 min | 21,455 |
| Mon | +6 min | 19,670 |
| Thu | +20 min | 18,573 |
| Sat | +23 min | 18,210 |
| Fri | **+36 min** (latest) | 17,281 |

The early group is **Sun/Mon/Tue/Wed** — precisely the nights before a Mon–Thu
commute. The late group is **Thu/Fri/Sat** — precisely the nights before a morning
with no drive (the last-to-bed person works from home on Fridays).

A single binary "commute tomorrow" flag is worth **+3,489 ± 560 revs** (t = 6.2)
and reaches R² = 0.509 with *one* parameter, versus 0.545 with all seven day
dummies. The schedule is a better model than the free-form weekly one.

### Caveats on the lights-out times

- **The absolute clock times are not identified.** Recovering one requires assuming
  revs → 0 as darkness → 0, i.e. that she runs the *entire* dark window. She doesn't —
  total revs ÷ 4,482 implies only ~4.4 effective hours inside a 7–9 hour window. So the
  fit extrapolates to a zero-crossing around 1 a.m., which is not anyone's bedtime.
  **Trust the offsets, not the clock times.** (Add a trend term and every absolute time
  slides ~2.5 hours earlier while the offsets keep the same rank order.)
- **The weekly pattern is *assumed* to be lights-out timing.** Statistically it is
  indistinguishable from any other weekly habit — Friday-night handling, weekend noise,
  cage-cleaning night. The plausible ordering is supporting evidence, not proof.

## Why `index.html` tiers on a trailing 30-day window

This analysis is what motivated the tier change. Under all-time percentile
thresholds, the tiers measured the season rather than the hamster:

| Month | All-time (old): low / high | Trailing 30d (new): low / high |
|---|---|---|
| Feb | 4% / **57%** | 29% / 21% |
| Apr | 13% / 20% | 50% / 17% |
| Jun | 53% / **0%** | 30% / 13% |
| Jul | 62% / **0%** | 38% / 23% |

By summer **no night could reach the "high" tier** and the all-time record had been
unbeatable since January — the gamification was dead for half the year. A trailing
window slides with the daylight, so a good night reads as good year-round. The
record stays all-time on purpose: it's the rare prize, and it comes back into reach
as the nights lengthen.

## The open question: autumn

Everything here rests on under six months of data that never completes a seasonal
cycle. **Autumn is the real test.** The model predicts revs climb back toward winter
levels as the nights lengthen. If they don't, there *is* a genuine slowdown hiding
underneath the photoperiod effect, and the coefficients need refitting.

Re-run the script when the autumn data is in. The lines to watch:

- `residual trend once dark window is controlled` — if this goes significant, she really
  is slowing down.
- `NATURAL EXPERIMENT 2` — a persistent negative bias on the photoperiod model would mean
  it is over-predicting, i.e. she is no longer keeping up with the lengthening nights.

## Method notes

- Sunrise: NOAA solar calculator, official sunrise (90.833° zenith), accurate to ~1–2 min.
- US Eastern time is implemented directly rather than via `zoneinfo`, because Windows
  Python frequently ships without `tzdata`. Getting DST right is load-bearing here — the
  8 March discontinuity *is* one of the three identification strategies.
- The night credited to a given "Date Checked" is taken to run from the evening *before*
  it to sunrise *on* it. Both alignments were tested; they fit within 0.001 R² of each
  other, so this choice is not doing any work.
- The 10 p.m. reference lights-out is arbitrary. A constant offset is absorbed into the
  intercept, so the fit is invariant to it — the model never needs to know the real
  bedtime, only that it is roughly constant within a weekday.
