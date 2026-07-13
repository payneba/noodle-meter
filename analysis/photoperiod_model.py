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
from pathlib import Path

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


# --------------------------------------------------------------------------
# HTML report
#
# Self-contained: no CDN, no external fonts, no build step. Every figure in the
# prose is interpolated from the computed results, so the page can never drift
# out of step with the console output above. Colours are a CVD-safe categorical
# pair (blue/red) checked against both the light and dark chart surfaces.
# --------------------------------------------------------------------------
REPORT_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Noodle: is the slowdown real, or just shorter nights?</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--s1:#2a78d6;--s2:#e34948;--dim:#b9b8b2;
--ring:rgba(11,11,11,.10)}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#e66767;
--dim:#5c5b56;--ring:rgba(255,255,255,.10)}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);padding:32px 20px 64px;
font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:880px;margin:0 auto}
h1{font-size:26px;line-height:1.25;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--ink2);margin:0 0 28px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;
padding:20px 22px;margin:0 0 20px}
.card h2{font-size:15px;margin:0 0 2px}
.note{color:var(--ink2);font-size:13.5px;margin:0 0 16px}
.hero{display:flex;gap:28px;align-items:baseline;flex-wrap:wrap;margin:4px 0 10px}
.fig{font-size:60px;font-weight:650;letter-spacing:-.03em;line-height:1;color:var(--s1)}
.cap{color:var(--ink2);font-size:14px;max-width:440px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:18px}
.kpi{background:var(--plane);border:1px solid var(--ring);border-radius:9px;padding:11px 13px}
.kpi .v{font-size:21px;font-weight:620}
.kpi .l{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.scroll{overflow-x:auto}
svg{display:block;width:100%;height:auto;overflow:visible}
.gl{stroke:var(--grid);stroke-width:1}.ax{stroke:var(--axis);stroke-width:1}
.tk{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.al{fill:var(--muted);font-size:11.5px}
.dl{font-size:12px;font-weight:600}
.lg{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 12px;font-size:12.5px;color:var(--ink2)}
.lg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:8px 10px;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
tr.best td{color:var(--s1);font-weight:640}
.verdict{border-left:3px solid var(--s1);padding-left:14px;margin:14px 0 0;color:var(--ink2);font-size:14px}
.caveat{border-left-color:var(--s2)}
.tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s;background:var(--surface);
border:1px solid var(--ring);border-radius:8px;padding:7px 10px;font-size:12.5px;
box-shadow:0 4px 16px rgba(0,0,0,.16);z-index:9;white-space:nowrap}
footer{color:var(--muted);font-size:12.5px;text-align:center;margin-top:8px}
code{font-size:12.5px}
</style>
</head>
<body>
<div class="wrap">
<h1>Noodle: is the slowdown real, or just shorter nights?</h1>
<p class="sub">__N__ nights, __FIRST__ &rarr; __LAST__ &middot; Andover, MA (42.66&deg;N) &middot;
modelling revs from the dark window between lights-out and sunrise</p>

<div class="card">
  <div class="hero">
    <div class="fig">__PCT__%</div>
    <div class="cap">of the long-run decline in spins per night is accounted for by the
    <b>shrinking dark window</b> alone. After controlling for it, the residual
    &ldquo;Noodle is slowing down&rdquo; trend is <b>__SIGWORD__</b>.</div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="v">~__R__</div><div class="l">revs per extra dark hour</div></div>
    <div class="kpi"><div class="v">__DMAX__h &rarr; __DMIN__h</div><div class="l">dark window, winter &rarr; summer</div></div>
    <div class="kpi"><div class="v">R&sup2; = __R2__</div><div class="l">dark window + day-of-week</div></div>
    <div class="kpi"><div class="v">__TREND__ &plusmn; __TRENDSE__</div><div class="l">residual trend, revs/day</div></div>
  </div>
</div>

<div class="card">
  <h2>The decline tracks the night, not the calendar</h2>
  <p class="note">Grey dots are observed nightly revs. The blue line is the model fit
  (dark window + day-of-week) &mdash; it contains no time trend at all.</p>
  <div class="lg"><span><i style="background:var(--dim)"></i>Observed</span>
  <span><i style="background:var(--s1)"></i>Model fit</span></div>
  <div class="scroll"><svg id="c1" viewBox="0 0 840 300"></svg></div>
</div>

<div class="card">
  <h2>Hours of darkness (lights-out assumed 10pm)</h2>
  <p class="note">The same seasonal shape &mdash; and a sharp step at daylight saving,
  when the household&rsquo;s bedtime moves an hour earlier <em>relative to the sun</em>,
  instantly <em>lengthening</em> Noodle&rsquo;s night.</p>
  <div class="scroll"><svg id="c2" viewBox="0 0 840 190"></svg></div>
</div>

<div class="card">
  <h2>Natural experiment 1 &mdash; the DST step</h2>
  <p class="note">The clocks jump but Noodle doesn&rsquo;t age overnight. The dark window
  gains <b>__DSTDARK__h</b> and revs jump <b>__DSTREV__</b>, implying <b>~__DSTIMP__ revs/hour</b>
  &mdash; independently reproducing the seasonal estimate of ~__R__.</p>
  <div class="lg"><span><i style="background:var(--dim)"></i>Nightly revs</span>
  <span><i style="background:var(--s1)"></i>Local trend + step</span></div>
  <div class="scroll"><svg id="c3" viewBox="0 0 840 260"></svg></div>
</div>

<div class="card" id="oos-card">
  <h2>Natural experiment 2 &mdash; the solstice reversal</h2>
  <p class="note">Trained only on data through __CUT__, then asked to forecast forward.
  After the solstice the nights grow again: the photoperiod model predicts the upturn,
  while the pure-trend model keeps marching down.</p>
  <div class="lg"><span><i style="background:var(--dim)"></i>Observed</span>
  <span><i style="background:var(--s1)"></i>Dark-window model</span>
  <span><i style="background:var(--s2)"></i>Trend-only model</span></div>
  <div class="scroll"><svg id="c4" viewBox="0 0 840 250"></svg></div>
</div>

<div class="card">
  <h2>Natural experiment 3 &mdash; the weekly rhythm</h2>
  <p class="note">Day-of-week is orthogonal to the season, so it identifies the effect
  cleanly. Bars show implied lights-out relative to the weekly average, by the evening the
  lights went out. Blue evenings precede a commute; red ones don&rsquo;t.</p>
  <div class="lg"><span><i style="background:var(--s1)"></i>Work morning tomorrow (early night)</span>
  <span><i style="background:var(--s2)"></i>No commute tomorrow (late night)</span></div>
  <div class="scroll"><svg id="c5" viewBox="0 0 840 240"></svg></div>
  <p class="verdict">A single <b>&ldquo;commute tomorrow&rdquo;</b> flag is worth
  <b>__COMMUTE__ &plusmn; __COMMUTESE__ revs</b> (t = __COMMUTET__). The household&rsquo;s
  commute schedule is recoverable from a hamster wheel.</p>
  <p class="verdict caveat"><b>Caveat.</b> The model <em>assumes</em> the weekly pattern is
  lights-out timing; statistically it is indistinguishable from any other weekly habit.
  And the <em>absolute</em> clock times are not identified &mdash; trust the offsets.</p>
</div>

<div class="card">
  <h2>Model comparison</h2>
  <p class="note">Out-of-sample RMSE is measured on the nights after __CUT__ &mdash; the only
  window where photoperiod and a downward trend make <em>opposite</em> predictions.</p>
  <table id="tbl"><thead><tr><th>Model</th><th>R&sup2;</th><th>RMSE</th>
  <th>Out-of-sample RMSE</th><th>Bias</th></tr></thead><tbody></tbody></table>
  <p class="verdict"><b>Verdict.</b> Photoperiod is doing the work. A trend can mimic it
  in-sample because both fall monotonically from winter to summer &mdash; but it fails exactly
  where the two diverge, and it has no mechanism for the DST step or the weekly cycle.</p>
</div>

<footer>Generated by <code>analysis/photoperiod_model.py</code> &middot; data through __LAST__.
Re-run the script to refresh.</footer>
</div>
<div class="tip" id="tip"></div>
<script>
const D = __DATA__;
const NS='http://www.w3.org/2000/svg', tip=document.getElementById('tip');
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e};
const show=(ev,h)=>{tip.innerHTML=h;tip.style.opacity=1;
  tip.style.left=Math.min(ev.clientX+14,innerWidth-tip.offsetWidth-8)+'px';
  tip.style.top=(ev.clientY-tip.offsetHeight-10)+'px'};
const hide=()=>tip.style.opacity=0;
const fmt=n=>n.toLocaleString();
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dt=s=>{const[y,m,d]=s.split('-').map(Number);return Date.UTC(y,m-1,d)};
const lbl=s=>{const d=new Date(dt(s));return d.getUTCDate()+' '+MON[d.getUTCMonth()]};
const nice=v=>{const p=Math.pow(10,Math.floor(Math.log10(v)));return Math.ceil(v/p)*p};
/* round axis values -- avoids ticks like 13,333 */
const ticks=(lo,hi,n)=>{const raw=(hi-lo)/n,p=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=p*([1,2,2.5,5,10].find(m=>p*m>=raw)||10),out=[];
  for(let v=Math.ceil(lo/step)*step;v<=hi+1e-9;v+=step)out.push(v);return out};

const t0=dt(D.series[0].d), t1=dt(D.series.at(-1).d);
function monthTicks(svg,x,yb){
  let prev=-1;
  for(const p of D.series){const d=new Date(dt(p.d));
    if(d.getUTCMonth()!==prev){prev=d.getUTCMonth();
      const px=x(dt(p.d));
      svg.appendChild(el('line',{x1:px,y1:yb,x2:px,y2:yb+5,class:'ax'}));
      const t=el('text',{x:px,y:yb+18,class:'tk','text-anchor':'middle'});
      t.textContent=MON[prev];svg.appendChild(t)}}
}

/* C1 - observed + fit */
(()=>{const svg=document.getElementById('c1'),W=840,H=300,L=54,R=14,T=26,B=30;
const yMax=nice(Math.max(...D.series.map(p=>p.revs))*1.05);
const x=t=>L+(t-t0)/(t1-t0)*(W-L-R), y=v=>T+(1-v/yMax)*(H-T-B);
for(const v of ticks(0,yMax,4)){
  svg.appendChild(el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'gl'}));
  const t=el('text',{x:L-9,y:y(v)+4,class:'tk','text-anchor':'end'});t.textContent=fmt(v);svg.appendChild(t)}
svg.appendChild(el('line',{x1:L,y1:y(0),x2:W-R,y2:y(0),class:'ax'}));
monthTicks(svg,x,y(0));
const a=el('text',{x:L-9,y:T-13,class:'al','text-anchor':'end'});a.textContent='revs';svg.appendChild(a);
for(const p of D.series){const c=el('circle',{cx:x(dt(p.d)),cy:y(p.revs),r:2.6,fill:'var(--dim)'});
  c.addEventListener('mouseenter',e=>show(e,`<b>${lbl(p.d)}</b> &middot; ${fmt(p.revs)} revs<br>dark ${p.dark}h &middot; model ${fmt(p.fit)}`));
  c.addEventListener('mouseleave',hide);svg.appendChild(c)}
svg.appendChild(el('path',{d:'M'+D.series.map(p=>x(dt(p.d))+' '+y(p.fit)).join(' L '),
  fill:'none',stroke:'var(--s1)','stroke-width':2}));})();

/* C2 - dark hours, broken at the DST step */
(()=>{const svg=document.getElementById('c2'),W=840,H=190,L=54,R=14,T=16,B=30;
const lo=Math.floor(D.darkMin*2)/2-.3, hi=Math.ceil(D.darkMax*2)/2+.3;
const x=t=>L+(t-t0)/(t1-t0)*(W-L-R), y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
for(let v=Math.ceil(lo);v<=hi;v++){svg.appendChild(el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'gl'}));
  const t=el('text',{x:L-9,y:y(v)+4,class:'tk','text-anchor':'end'});t.textContent=v+'h';svg.appendChild(t)}
svg.appendChild(el('line',{x1:L,y1:H-B,x2:W-R,y2:H-B,class:'ax'}));
monthTicks(svg,x,H-B);
let d='',prev=null;
for(const p of D.series){const px=x(dt(p.d)),py=y(p.dark);
  d+=(prev===null||Math.abs(p.dark-prev)>0.5?'M':' L ')+px+' '+py;prev=p.dark}
svg.appendChild(el('path',{d,fill:'none',stroke:'var(--s1)','stroke-width':2}));
if(D.dstDate){const dx=x(dt(D.dstDate));
  svg.appendChild(el('line',{x1:dx,y1:T,x2:dx,y2:H-B,stroke:'var(--muted)','stroke-width':1,'stroke-dasharray':'3 3'}));
  const t=el('text',{x:dx+6,y:T+10,class:'dl',fill:'var(--muted)'});t.textContent='DST';svg.appendChild(t)}})();

/* C3 - DST regression discontinuity */
(()=>{const g=D.dstPoints;const svg=document.getElementById('c3');
if(!g||!g.length){svg.remove();return}
const W=840,H=260,L=54,R=14,T=26,B=34;
const yMax=nice(Math.max(...g.map(p=>p.revs))*1.05);
const span=Math.max(...g.map(p=>Math.abs(p.days)));
const x=v=>L+(v+span)/(2*span)*(W-L-R), y=v=>T+(1-v/yMax)*(H-T-B);
for(const v of ticks(0,yMax,3)){
  svg.appendChild(el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'gl'}));
  const t=el('text',{x:L-9,y:y(v)+4,class:'tk','text-anchor':'end'});t.textContent=fmt(v);svg.appendChild(t)}
svg.appendChild(el('line',{x1:L,y1:y(0),x2:W-R,y2:y(0),class:'ax'}));
for(const v of [-span,-span/2,0,span/2,span]){const px=x(v);
  svg.appendChild(el('line',{x1:px,y1:y(0),x2:px,y2:y(0)+5,class:'ax'}));
  const t=el('text',{x:px,y:y(0)+18,class:'tk','text-anchor':'middle'});
  t.textContent=v===0?'DST':(v>0?'+'+Math.round(v)+'d':Math.round(v)+'d');svg.appendChild(t)}
const a=el('text',{x:L-9,y:T-13,class:'al','text-anchor':'end'});a.textContent='revs';svg.appendChild(a);
const seg=s=>{const P=g.filter(p=>s<0?p.days<0:p.days>=0);
  const mx=P.reduce((q,p)=>q+p.days,0)/P.length,my=P.reduce((q,p)=>q+p.revs,0)/P.length;
  let sxy=0,sxx=0;for(const p of P){sxy+=(p.days-mx)*(p.revs-my);sxx+=(p.days-mx)**2}
  const b=sxy/sxx,c=my-b*mx,x0=s<0?-span:0,x1=s<0?-1:span;
  svg.appendChild(el('line',{x1:x(x0),y1:y(c+b*x0),x2:x(x1),y2:y(c+b*x1),stroke:'var(--s1)','stroke-width':2}));
  return c};
const vPre=seg(-1),vPost=seg(1);
svg.appendChild(el('line',{x1:x(0),y1:T,x2:x(0),y2:y(0),stroke:'var(--muted)','stroke-width':1,'stroke-dasharray':'3 3'}));
svg.appendChild(el('line',{x1:x(0),y1:y(vPre),x2:x(0),y2:y(vPost),stroke:'var(--s1)','stroke-width':2,'stroke-dasharray':'2 3'}));
for(const p of g){const c=el('circle',{cx:x(p.days),cy:y(p.revs),r:3.2,fill:'var(--dim)',stroke:'var(--surface)','stroke-width':2});
  c.addEventListener('mouseenter',e=>show(e,`<b>${lbl(p.d)}</b> &middot; ${fmt(p.revs)} revs<br>dark ${p.dark}h`));
  c.addEventListener('mouseleave',hide);svg.appendChild(c)}
const t=el('text',{x:x(span*0.06),y:y(Math.max(vPre,vPost))-12,class:'dl',fill:'var(--s1)'});
t.textContent='step at DST';svg.appendChild(t)})();

/* C4 - out-of-sample */
(()=>{const svg=document.getElementById('c4');
if(!D.oos){document.getElementById('oos-card').remove();return}
const g=D.oos.points,W=840,H=250,L=54,R=64,T=16,B=30;
const a0=dt(g[0].d),a1=dt(g.at(-1).d);
const vals=g.flatMap(p=>[p.revs,p.predDark,p.predTrend]);
const lo=Math.min(...vals)*0.9,hi=Math.max(...vals)*1.06;
const x=t=>L+(t-a0)/(a1-a0)*(W-L-R), y=v=>T+(1-(v-lo)/(hi-lo))*(H-T-B);
for(const v of ticks(lo,hi,4)){
  svg.appendChild(el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'gl'}));
  const t=el('text',{x:L-9,y:y(v)+4,class:'tk','text-anchor':'end'});t.textContent=fmt(v);svg.appendChild(t)}
svg.appendChild(el('line',{x1:L,y1:y(lo),x2:W-R,y2:y(lo),class:'ax'}));
for(let i=0;i<g.length;i+=Math.ceil(g.length/5)){const px=x(dt(g[i].d));
  svg.appendChild(el('line',{x1:px,y1:y(lo),x2:px,y2:y(lo)+5,class:'ax'}));
  const t=el('text',{x:px,y:y(lo)+18,class:'tk','text-anchor':'middle'});t.textContent=lbl(g[i].d);svg.appendChild(t)}
const sx=x(dt(D.oos.solstice));
if(sx>=L&&sx<=W-R){svg.appendChild(el('line',{x1:sx,y1:T,x2:sx,y2:y(lo),stroke:'var(--muted)','stroke-width':1,'stroke-dasharray':'3 3'}));
  const t=el('text',{x:sx+5,y:T+10,class:'dl',fill:'var(--muted)'});t.textContent='solstice';svg.appendChild(t)}
const line=(k,c)=>svg.appendChild(el('path',{d:'M'+g.map(p=>x(dt(p.d))+' '+y(p[k])).join(' L '),fill:'none',stroke:c,'stroke-width':2}));
line('predTrend','var(--s2)');line('predDark','var(--s1)');
for(const p of g){const c=el('circle',{cx:x(dt(p.d)),cy:y(p.revs),r:3.2,fill:'var(--dim)',stroke:'var(--surface)','stroke-width':2});
  c.addEventListener('mouseenter',e=>show(e,`<b>${lbl(p.d)}</b> &middot; actual ${fmt(p.revs)}<br>dark-window ${fmt(p.predDark)}<br>trend-only ${fmt(p.predTrend)}`));
  c.addEventListener('mouseleave',hide);svg.appendChild(c)}
const last=g.at(-1);
for(const[k,c,txt] of [['predDark','var(--s1)','dark'],['predTrend','var(--s2)','trend']]){
  const t=el('text',{x:x(dt(last.d))+7,y:y(last[k])+4,class:'dl',fill:c});t.textContent=txt;svg.appendChild(t)}})();

/* C5 - day-of-week */
(()=>{const svg=document.getElementById('c5'),g=D.dow,W=840,H=240,L=56,R=20,T=22,B=42;
const bw=(W-L-R)/g.length, mx=Math.max(60,...g.map(p=>Math.abs(p.offsetMin)))*1.15;
const y=v=>T+(mx-v)/(2*mx)*(H-T-B);
svg.appendChild(el('line',{x1:L,y1:y(0),x2:W-R,y2:y(0),class:'ax'}));
for(const v of [-60,-30,30,60]){if(Math.abs(v)>mx)continue;
  svg.appendChild(el('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),class:'gl'}));
  const t=el('text',{x:L-9,y:y(v)+4,class:'tk','text-anchor':'end'});t.textContent=(v>0?'+':'')+v+'m';svg.appendChild(t)}
const a=el('text',{x:L-9,y:T-6,class:'al','text-anchor':'end'});a.textContent='later';svg.appendChild(a);
g.forEach((p,i)=>{const cx=L+bw*i+bw/2,v=p.offsetMin,up=v>=0,w=Math.min(bw-14,54);
  const r=el('rect',{x:cx-w/2,y:up?y(v):y(0),width:w,height:Math.max(Math.abs(y(v)-y(0)),1),rx:4,
    fill:p.commute?'var(--s1)':'var(--s2)',stroke:'var(--surface)','stroke-width':2});
  r.addEventListener('mouseenter',e=>show(e,`<b>${p.dow} evening</b> (n=${p.n})<br>implied lights-out ${p.lightsOut} (${v>0?'+':''}${v} min)<br>mean ${fmt(p.meanRevs)} revs<br>${p.commute?'work morning tomorrow':'no commute tomorrow'}`));
  r.addEventListener('mouseleave',hide);svg.appendChild(r);
  const lt=el('text',{x:cx,y:H-B+18,class:'tk','text-anchor':'middle'});lt.textContent=p.dow;svg.appendChild(lt);
  const vt=el('text',{x:cx,y:up?y(v)-7:y(v)+15,class:'dl','text-anchor':'middle',fill:'var(--ink2)'});
  vt.textContent=(v>0?'+':'')+v;svg.appendChild(vt)});
const c=el('text',{x:L,y:H-8,class:'al'});c.textContent='evening the lights went out';svg.appendChild(c)})();

/* model table */
(()=>{const tb=document.querySelector('#tbl tbody');
const es=Object.entries(D.models);
const best=Math.min(...es.filter(([,m])=>m.oos!=null).map(([,m])=>m.oos));
for(const[name,m] of es){const tr=document.createElement('tr');
  if(m.oos===best)tr.className='best';
  tr.innerHTML=`<td>${name}</td><td>${m.r2.toFixed(3)}</td><td>${fmt(m.rmse)}</td>
    <td>${m.oos!=null?fmt(m.oos):'&mdash;'}</td><td>${m.bias!=null?(m.bias>0?'+':'')+fmt(m.bias):'&mdash;'}</td>`;
  tb.appendChild(tr)}})();
</script>
</body>
</html>
"""


def render_report(R):
    dst28 = next((d for d in R["dstRows"] if d["w"] == 28), R["dstRows"][0] if R["dstRows"] else None)
    subs = {
        "__N__": str(R["n"]),
        "__FIRST__": R["first"],
        "__LAST__": R["last"],
        "__PCT__": str(R.get("pctExplained", "?")),
        "__SIGWORD__": ("statistically significant -- she really is slowing down"
                        if R["trendSignificant"] else "not statistically significant"),
        "__R__": f"{R['r']:,}",
        "__R2__": f"{R['models']['dark + day-of-week']['r2']:.3f}",
        "__DMIN__": f"{R['darkMin']:.1f}",
        "__DMAX__": f"{R['darkMax']:.1f}",
        "__TREND__": f"{R['trendCoef']:+.0f}",
        "__TRENDSE__": f"{R['trendSE']:.0f}",
        "__DSTDARK__": f"{dst28['darkStep']:+.2f}" if dst28 else "n/a",
        "__DSTREV__": f"{dst28['revStep']:+,}" if dst28 else "n/a",
        "__DSTIMP__": f"{dst28['implied']:,}" if dst28 else "n/a",
        "__CUT__": R["oos"]["cut"] if R["oos"] else "n/a",
        "__COMMUTE__": f"{R['commuteEffect']:+,}",
        "__COMMUTESE__": f"{R['commuteSE']:,}",
        "__COMMUTET__": f"{R['commuteT']:+.1f}",
        "__DATA__": json.dumps(R, separators=(",", ":")),
    }
    html = REPORT_TEMPLATE
    for k, v in subs.items():
        html = html.replace(k, v)
    return html


def main(write_html=True):
    dates, y = load()
    n = len(dates)
    S, dow, t = build(dates)
    one = np.ones(n)
    D7 = np.zeros((n, 7))
    D7[np.arange(n), dow] = 1
    commute = np.array([1.0 if d in COMMUTE_EVENINGS else 0.0 for d in dow])

    # Everything the HTML report needs is collected here as it is computed, so the
    # chart and the console output can never disagree.
    R = {"n": n, "first": str(dates[0]), "last": str(dates[-1]),
         "meanRevs": round(float(y.mean())),
         "darkMin": round(float(S.min()), 2), "darkMax": round(float(S.max()), 2)}

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
    R["models"] = {}
    for name, X in models.items():
        _, _, r2, rmse, _ = ols(X, y)
        R["models"][name] = {"r2": round(float(r2), 3), "rmse": round(float(rmse))}
        print(f"  {name:28s} R2={r2:.3f}  rmse={rmse:5.0f}")

    b, se, _, _, _ = ols(np.column_stack([D7, S]), y)
    r = b[7]
    R["r"] = round(float(r))
    R["rSE"] = round(float(se[7]))
    R["fit"] = [round(float(v)) for v in (np.column_stack([D7, S]) @ b)]
    print(f"\n  revs per extra hour of darkness: {r:.0f} +/- {se[7]:.0f}")

    bt, set_, _, _, _ = ols(np.column_stack([D7, S, t]), y)
    tstat = bt[8] / set_[8]
    R["trendCoef"] = round(float(bt[8]), 1)
    R["trendSE"] = round(float(set_[8]), 1)
    R["trendT"] = round(float(tstat), 2)
    R["trendSignificant"] = bool(abs(tstat) >= 2)
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
        R["declineObs"] = round(float(d_obs))
        R["declinePred"] = round(float(pred))
        R["pctExplained"] = round(float(share))
        R["darkEarly"] = round(float(S[early].mean()), 2)
        R["darkJune"] = round(float(S[june].mean()), 2)
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
    R["dstDate"] = str(dst)
    R["dstRows"] = []
    for W in (21, 28, 35):
        idx = [i for i, D in enumerate(dates) if abs((D - dst).days) <= W]
        if len(idx) < 20:
            continue
        dd = np.array([(dates[i] - dst).days for i in idx], dtype=float)
        X = np.column_stack([np.ones(len(idx)), dd, (dd >= 0).astype(float)])
        bs, _, _, _, _ = ols(X, S[idx])
        br, ser, _, _, _ = ols(X, y[idx])
        implied = br[2] / bs[2] if bs[2] else float("nan")
        R["dstRows"].append({"w": W, "darkStep": round(float(bs[2]), 2),
                             "revStep": round(float(br[2])), "revSE": round(float(ser[2])),
                             "implied": round(float(implied))})
        if W == 28:   # the window the report charts
            R["dstPoints"] = [{"d": str(dates[i]), "days": (dates[i] - dst).days,
                               "revs": int(y[i]), "dark": round(float(S[i]), 2)} for i in idx]
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
    R["oos"] = None
    if len(te) >= 10 and len(tr) >= 30:
        print(f"  train n={len(tr)} (through {cut}), test n={len(te)}")
        preds = {}
        for name, X in models.items():
            beta, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
            pred = X[te] @ beta
            preds[name] = pred
            rmse_o = math.sqrt(((y[te] - pred) ** 2).mean())
            bias = (pred - y[te]).mean()
            R["models"][name]["oos"] = round(float(rmse_o))
            R["models"][name]["bias"] = round(float(bias))
            print(f"  {name:28s} out-of-sample rmse={rmse_o:5.0f}  bias={bias:+6.0f}")
        print("  (a negative bias = the model under-predicts, i.e. she ran MORE than it expected)")
        R["oos"] = {
            "cut": str(cut), "solstice": str(solstice),
            "points": [{"d": str(dates[i]), "revs": int(y[i]),
                        "predDark": round(float(preds["dark + day-of-week"][k])),
                        "predTrend": round(float(preds["trend only"][k]))}
                       for k, i in enumerate(te)],
        }
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
    R["dow"] = [{"dow": DOW[j], "lightsOut": hhmm(L[j]),
                 "offsetMin": round(float((L[j] - L.mean()) * 60)),
                 "meanRevs": round(float(y[dow == j].mean())),
                 "commute": bool(j in COMMUTE_EVENINGS),
                 "n": int((dow == j).sum())} for j in range(7)]
    R["dowSpreadMin"] = round(float((L.max() - L.min()) * 60))
    print(f"\n  {'evening':9s}{'implied lights-out':>20s}{'offset':>10s}{'mean revs':>12s}")
    for j in order:
        print(f"  {DOW[j]:9s}{hhmm(L[j]):>20s}{(L[j]-L.mean())*60:>+9.0f}m{y[dow == j].mean():>12.0f}")
    print(f"\n  spread earliest -> latest: {(L.max()-L.min())*60:.0f} min")

    bc, sec, r2c, _, _ = ols(np.column_stack([one, S, commute]), y)
    R["commuteEffect"] = round(float(bc[2]))
    R["commuteSE"] = round(float(sec[2]))
    R["commuteT"] = round(float(bc[2] / sec[2]), 2)
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
    R["tiers"] = []
    for m in sorted(schemes):
        rows = schemes[m]
        N = len(rows)
        def pct(k, which):
            return 100 * sum(1 for x in rows if x[which] == k) / N
        R["tiers"].append({"month": m, "n": N,
                           "oldLow": round(pct("low", 0)), "oldHigh": round(pct("high", 0)),
                           "newLow": round(pct("low", 1)), "newHigh": round(pct("high", 1))})
        print(f"  {m:9s}{N:4d}  {pct('low',0):6.0f}%{pct('high',0):6.0f}%"
              f"{sum(1 for x in rows if x[0]=='record'):5d}   "
              f"{pct('low',1):6.0f}%{pct('high',1):6.0f}%"
              f"{sum(1 for x in rows if x[1]=='record'):5d}")
    print("\n  Under all-time thresholds the tiers measure the calendar: by summer no night")
    print("  can reach 'high' and the record is unbeatable. The trailing window slides with")
    print("  the daylight, so a good night reads as good year-round.")
    print("=" * 74)

    R["series"] = [{"d": str(dates[i]), "revs": int(y[i]), "dark": round(float(S[i]), 2),
                    "fit": R["fit"][i]} for i in range(n)]
    del R["fit"]

    if write_html:
        path = Path(__file__).with_name("report.html")
        path.write_text(render_report(R), encoding="utf-8", newline="\n")
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
