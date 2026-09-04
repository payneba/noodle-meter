# Multi-Pet Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the single-pet Noodle Meter into a multi-pet tracker: per-pet Google Form submission, per-pet config in `pets.json`, client-side distance/stats computation, and a pet switcher — while migrating Noodle onto the new pipeline.

**Architecture:** "Thin server, smart client." A single Google Apps Script deployment serves raw form-response rows per pet (`?pet=<slug>`, slug = sheet tab name). All computation (distance = revs × milesPerRev, dedup, tiers, stats) happens in the browser using config from `pets.json`. Pure computation functions are extracted from `index.html` into `stats.js` so Node can unit-test them.

**Tech Stack:** Static HTML/CSS/vanilla JS on GitHub Pages; Google Forms + Sheets + Apps Script; Node 20 for tests (homegrown harness, no npm dependencies); GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-09-04-multi-pet-design.md`

## Global Constraints

- Unix (LF) line endings in all files.
- No npm dependencies; tests run with plain `node tests.js`.
- Never prefix Bash commands with `cd <dir> &&`; run `git add` and `git commit` as separate Bash calls (user's permission-wildcard rules).
- Local page testing requires an HTTP server (fetch fails on file://): run `C:/Python314/python.exe -m http.server 8000` in the repo root and open `http://localhost:8000/`.
- Date strings throughout the app are `en-US` locale format (`M/d/yyyy`), produced by `new Date(x).toLocaleDateString('en-US')` — this matches the existing sheet's `Date Checked` semantics (the morning the wheel is read).
- Constants keep their current values: `TIER_WINDOW_DAYS = 30`, `HISTOGRAM_WINDOW_DAYS = 90`, `MIN_WINDOW_SAMPLES = 10`.
- In unit tests, use midday-UTC ISO timestamps (e.g. `2026-01-05T14:00:00Z`) so the local-date conversion lands on the same calendar day in both US timezones and CI's UTC.
- Task 3 requires human actions in the Google UI (forms, sheet, Apps Script deployment). The executor must stop and hand those steps to Brad, then resume.

---

### Task 1: Extract pure computation into `stats.js`; restructure tests

Splits the inline computation out of `index.html` with **no behavior change**, and reorganizes the test harness so unit suites can be added.

**Files:**
- Create: `stats.js`
- Create: `tests/harness.js`
- Create: `tests/unit_tests.js`
- Create: `tests/endpoint_tests.js` (existing endpoint checks moved here verbatim)
- Modify: `tests.js` (becomes the suite orchestrator)
- Modify: `index.html` (remove extracted functions, load `stats.js`, update call sites)

**Interfaces:**
- Produces: global `Stats` in the browser / `module.exports` in Node, with:
  - `Stats.TIER_WINDOW_DAYS`, `Stats.HISTOGRAM_WINDOW_DAYS`, `Stats.MIN_WINDOW_SAMPLES` (numbers)
  - `Stats.calculatePercentile(arr, p)` → number
  - `Stats.windowThresholds(distances)` → `{p25, p75, max}`
  - `Stats.trailingDistances(data, i, days)` → array of distances (note: takes `data` as a parameter now, entries need `{date, distance}`)
  - `Stats.computeTiers(data)` → mutates each entry to add `.tier` ('low'|'medium'|'high'|'record') and `.windowBest` (bool); **returns** the all-time `{p25, p75, max}` thresholds
- Produces: `tests/harness.js` exporting `{test, assertEqual, assertTrue, assertClose, summary}`; each suite file exports `async run(harness)`.

- [ ] **Step 1: Write `tests/harness.js`**

```javascript
// Shared test harness for Noodle Meter test suites.
let passed = 0;
let failed = 0;

function test(name, fn) {
    try {
        fn();
        console.log(`✓ ${name}`);
        passed++;
    } catch (error) {
        console.log(`✗ ${name}`);
        console.log(`  Error: ${error.message}`);
        failed++;
    }
}

function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(`${message}: expected ${expected}, got ${actual}`);
    }
}

function assertTrue(condition, message) {
    if (!condition) {
        throw new Error(message);
    }
}

function assertClose(actual, expected, tolerance, message) {
    if (Math.abs(actual - expected) > tolerance) {
        throw new Error(`${message}: expected ~${expected} (±${tolerance}), got ${actual}`);
    }
}

function summary() {
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(failed > 0 ? 1 : 0);
}

module.exports = { test, assertEqual, assertTrue, assertClose, summary };
```

- [ ] **Step 2: Move the existing endpoint tests into `tests/endpoint_tests.js`**

Copy the `fetch` helper and tests 1–7 from the current `tests.js` unchanged, wrapped as a suite (this file is rewritten for the new contract in Task 6; keeping it green in the interim proves the move itself broke nothing):

```javascript
// Endpoint tests: validate the live Apps Script data endpoint.
const https = require('https');

const DATA_URL = 'https://script.google.com/macros/s/AKfycbxoKRMGYPQAxMCUerc8ZO2MPxJl_aeTZRwIzMYej86asddpN4IzkjgOggQMnLtKUCIzuQ/exec';

function fetchUrl(url) {
    return new Promise((resolve, reject) => {
        const makeRequest = (url) => {
            https.get(url, (res) => {
                if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    makeRequest(res.headers.location);
                    return;
                }
                if (res.statusCode !== 200) {
                    reject(new Error(`HTTP ${res.statusCode}`));
                    return;
                }
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => resolve({ data, status: res.statusCode }));
            }).on('error', reject);
        };
        makeRequest(url);
    });
}

async function run(h) {
    console.log('\nEndpoint tests');

    let responseData;
    try {
        const response = await fetchUrl(DATA_URL);
        h.test('Apps Script endpoint responds with 200', () => {
            h.assertEqual(response.status, 200, 'Status code');
        });
        responseData = response.data;
    } catch (error) {
        h.test('Apps Script endpoint responds with 200', () => { throw error; });
        return;
    }

    let jsonData;
    h.test('Response is valid JSON', () => {
        jsonData = JSON.parse(responseData);
    });
    h.test('Response is an array', () => {
        h.assertTrue(Array.isArray(jsonData), 'Response should be an array');
    });
    h.test('Response contains data', () => {
        h.assertTrue(jsonData.length > 0, 'Array should not be empty');
    });
    h.test('Data has expected fields (date, revs, distance)', () => {
        const first = jsonData[0];
        h.assertTrue('date' in first, 'Missing date field');
        h.assertTrue('revs' in first, 'Missing revs field');
        h.assertTrue('distance' in first, 'Missing distance field');
    });
    h.test('Distance values are reasonable (0-50 miles)', () => {
        jsonData.forEach((row, i) => {
            const dist = Number(row.distance);
            h.assertTrue(dist >= 0 && dist <= 50, `Row ${i}: distance ${dist} out of range`);
        });
    });
    h.test('Revolution counts are positive', () => {
        jsonData.forEach((row, i) => {
            const revs = Number(row.revs);
            h.assertTrue(revs >= 0, `Row ${i}: revs ${revs} should be positive`);
        });
    });
}

module.exports = { run };
```

- [ ] **Step 3: Rewrite `tests.js` as the orchestrator**

```javascript
// Test runner for Noodle Meter. Run with: node tests.js
const harness = require('./tests/harness');

(async () => {
    console.log('Running Noodle Meter Tests');
    await require('./tests/unit_tests').run(harness);
    await require('./tests/endpoint_tests').run(harness);
    harness.summary();
})();
```

- [ ] **Step 4: Write the failing unit tests in `tests/unit_tests.js`**

```javascript
// Unit tests for stats.js pure computation functions.
const Stats = require('../stats.js');

// Consecutive daily entries starting at startDate (en-US date strings).
function mkData(distances, startDate) {
    const out = [];
    const d = new Date(startDate);
    distances.forEach(dist => {
        out.push({ date: d.toLocaleDateString('en-US'), distance: dist });
        d.setDate(d.getDate() + 1);
    });
    return out;
}

async function run(h) {
    console.log('\nUnit tests (stats.js)');

    h.test('constants exported', () => {
        h.assertEqual(Stats.TIER_WINDOW_DAYS, 30, 'TIER_WINDOW_DAYS');
        h.assertEqual(Stats.HISTOGRAM_WINDOW_DAYS, 90, 'HISTOGRAM_WINDOW_DAYS');
        h.assertEqual(Stats.MIN_WINDOW_SAMPLES, 10, 'MIN_WINDOW_SAMPLES');
    });

    h.test('percentile of single element', () => {
        h.assertEqual(Stats.calculatePercentile([5], 50), 5, 'p50');
    });

    h.test('percentile interpolates', () => {
        h.assertEqual(Stats.calculatePercentile([0, 10], 50), 5, 'p50 of [0,10]');
    });

    h.test('windowThresholds', () => {
        const t = Stats.windowThresholds([1, 2, 3, 4, 5]);
        h.assertEqual(t.p25, 2, 'p25');
        h.assertEqual(t.p75, 4, 'p75');
        h.assertEqual(t.max, 5, 'max');
    });

    h.test('trailingDistances excludes current entry, respects window', () => {
        const data = mkData([1, 2, 3, 4], '1/1/2026');
        const past = Stats.trailingDistances(data, 3, 2);
        h.assertEqual(past.length, 2, 'entries within 2-day window');
        h.assertEqual(past[0], 3, 'most recent first');
        h.assertEqual(past[1], 2, 'older second');
    });

    h.test('computeTiers falls back to all-time with sparse history', () => {
        const data = mkData([1, 2, 3, 4], '1/1/2026');
        const thresholds = Stats.computeTiers(data);
        h.assertEqual(thresholds.max, 4, 'all-time max returned');
        h.assertEqual(data[3].tier, 'record', 'max entry is record');
        h.assertEqual(data[2].tier, 'medium', '3 is medium (not > p75=3.25)');
        h.assertEqual(data[1].tier, 'medium', '2 is medium (>= p25=1.75)');
        h.assertEqual(data[0].tier, 'low', '1 is low');
        h.assertEqual(data[3].windowBest, false, 'no windowBest without enough samples');
    });

    h.test('computeTiers uses trailing window and sets windowBest', () => {
        const distances = Array(14).fill(5).concat([6]);
        const data = mkData(distances, '1/1/2026');
        Stats.computeTiers(data);
        h.assertEqual(data[14].tier, 'record', 'all-time max is record');
        h.assertEqual(data[14].windowBest, true, 'beats every night in window');
        h.assertEqual(data[10].tier, 'medium', 'mid-pack night is medium');
    });
}

module.exports = { run };
```

- [ ] **Step 5: Run tests to verify the unit suite fails**

Run: `node tests.js`
Expected: FAIL — `Cannot find module '../stats.js'` (endpoint suite may still pass).

- [ ] **Step 6: Create `stats.js`**

Lifted from `index.html` with two deliberate changes: `trailingDistances` takes `data` as its first parameter (no global), and `computeTiers` computes the all-time thresholds itself and returns them.

```javascript
// stats.js — pure computation for Noodle Meter.
// Loaded by index.html as a browser global (Stats) and require()d by Node tests.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.Stats = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {

    // Pets run at night, from lights-out to sunrise, so a summer night gives ~2 fewer
    // hours of wheel time than a winter one. Grading against all-time thresholds
    // therefore just measures the season: every summer night scores "low" and the
    // record can never be beaten until winter. Grade against recent form instead --
    // the window slides with the daylight, so a good night reads as good year-round.
    const TIER_WINDOW_DAYS = 30;
    const HISTOGRAM_WINDOW_DAYS = 90;
    const MIN_WINDOW_SAMPLES = 10;

    function calculatePercentile(arr, p) {
        const sorted = [...arr].sort((a, b) => a - b);
        const index = (p / 100) * (sorted.length - 1);
        const lower = Math.floor(index);
        const upper = Math.ceil(index);
        if (lower === upper) return sorted[lower];
        return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
    }

    function windowThresholds(distances) {
        return {
            p25: calculatePercentile(distances, 25),
            p75: calculatePercentile(distances, 75),
            max: Math.max(...distances)
        };
    }

    // Entries from the N days immediately before entry i (excludes i itself).
    function trailingDistances(data, i, days) {
        const cutoff = new Date(data[i].date);
        cutoff.setDate(cutoff.getDate() - days);
        const out = [];
        for (let j = i - 1; j >= 0; j--) {
            if (new Date(data[j].date) < cutoff) break;
            out.push(data[j].distance);
        }
        return out;
    }

    // Assigns entry.tier and entry.windowBest to every entry; returns the
    // all-time {p25, p75, max} thresholds (used as the sparse-history fallback
    // here and for the histogram's record bucket).
    function computeTiers(data) {
        const allTime = windowThresholds(data.map(d => d.distance));
        data.forEach((entry, i) => {
            const past = trailingDistances(data, i, TIER_WINDOW_DAYS);
            // Not enough history behind this night to judge recent form; fall back
            // to all-time thresholds so the earliest entries still get a tier.
            const t = past.length >= MIN_WINDOW_SAMPLES
                ? windowThresholds(past)
                : allTime;

            entry.windowBest = past.length >= MIN_WINDOW_SAMPLES && entry.distance > t.max;

            if (entry.distance >= allTime.max) entry.tier = 'record';
            else if (entry.distance > t.p75) entry.tier = 'high';
            else if (entry.distance >= t.p25) entry.tier = 'medium';
            else entry.tier = 'low';
        });
        return allTime;
    }

    return {
        TIER_WINDOW_DAYS,
        HISTOGRAM_WINDOW_DAYS,
        MIN_WINDOW_SAMPLES,
        calculatePercentile,
        windowThresholds,
        trailingDistances,
        computeTiers
    };
}));
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `node tests.js`
Expected: PASS — all unit tests green, existing endpoint tests still green.

- [ ] **Step 8: Update `index.html` to use `stats.js`**

Add before the inline `<script>`:

```html
<script src="stats.js"></script>
```

Then in the inline script:
1. Delete the functions `calculatePercentile`, `windowThresholds`, `trailingDistances`, `computeTiers`, `calculateThresholds`, and the constants `TIER_WINDOW_DAYS`, `HISTOGRAM_WINDOW_DAYS`, `MIN_WINDOW_SAMPLES` (and the comment block above them — it now lives in stats.js).
2. In `processData`, replace:

```javascript
            calculateThresholds();
            computeTiers();
```

with:

```javascript
            thresholds = Stats.computeTiers(data);
```

3. In `showStatsView`, replace the two remaining references: `HISTOGRAM_WINDOW_DAYS` → `Stats.HISTOGRAM_WINDOW_DAYS`, `MIN_WINDOW_SAMPLES` → `Stats.MIN_WINDOW_SAMPLES`, and `windowThresholds(...)` → `Stats.windowThresholds(...)`.

`getTier`, `getBadge`, and everything DOM-related stay in `index.html` unchanged.

- [ ] **Step 9: Verify the page is unchanged in the browser**

Run: `C:/Python314/python.exe -m http.server 8000` (background), open `http://localhost:8000/`.
Expected: page loads exactly as before — today's distance, tier styling, stats view, histogram, activity grid all render; no console errors. Press Ctrl+Shift+R on the page first to bypass the localStorage cache. Kill the server afterwards.

- [ ] **Step 10: Commit**

```bash
git add stats.js tests.js tests/harness.js tests/unit_tests.js tests/endpoint_tests.js index.html
```

```bash
git commit -m "Extract pure stats computation into stats.js with unit tests"
```

---

### Task 2: Add `normalizeRows` and `milesPerRev` to `stats.js`

Pure additions (not yet wired into the page): the new-contract row normalizer and the per-pet distance factor.

**Files:**
- Modify: `stats.js`
- Modify: `tests/unit_tests.js`

**Interfaces:**
- Consumes: `stats.js` module shape from Task 1.
- Produces:
  - `Stats.milesPerRev(pet)` → number. `pet.milesPerRev` if set, else `Math.PI * pet.wheelDiameterInches / 63360`.
  - `Stats.normalizeRows(rows, perRev)` → `[{date, revs, distance}]` sorted ascending by date. `rows` are raw endpoint rows `{timestamp, revs, date}` where `date` is an optional override (empty string when absent). Effective date = override if present else timestamp's local date, formatted `en-US`. Duplicate effective dates: **last row wins**. Rows with non-numeric/blank revs or unparseable dates are skipped.

- [ ] **Step 1: Add failing unit tests to `tests/unit_tests.js`** (inside `run`, after the existing tests)

```javascript
    h.test('milesPerRev from wheel diameter', () => {
        h.assertClose(Stats.milesPerRev({ wheelDiameterInches: 9 }),
            Math.PI * 9 / 63360, 1e-12, 'diameter-derived');
    });

    h.test('milesPerRev override wins over diameter', () => {
        h.assertEqual(Stats.milesPerRev({ wheelDiameterInches: 9, milesPerRev: 0.5 }),
            0.5, 'override');
    });

    h.test('normalizeRows computes distance from revs', () => {
        const out = Stats.normalizeRows(
            [{ timestamp: '2026-01-05T14:00:00Z', revs: 1000, date: '' }], 0.001);
        h.assertEqual(out.length, 1, 'one row');
        h.assertEqual(out[0].date, new Date('2026-01-05T14:00:00Z').toLocaleDateString('en-US'), 'date from timestamp');
        h.assertEqual(out[0].revs, 1000, 'revs');
        h.assertClose(out[0].distance, 1, 1e-9, 'distance');
    });

    h.test('normalizeRows honors date override', () => {
        const out = Stats.normalizeRows(
            [{ timestamp: '2026-01-05T14:00:00Z', revs: 500, date: '1/3/2026' }], 0.001);
        h.assertEqual(out[0].date, '1/3/2026', 'override used');
    });

    h.test('normalizeRows dedupes by date, last submission wins', () => {
        const out = Stats.normalizeRows([
            { timestamp: '2026-01-05T14:00:00Z', revs: 100, date: '' },
            { timestamp: '2026-01-05T16:00:00Z', revs: 200, date: '' }
        ], 0.001);
        h.assertEqual(out.length, 1, 'deduped');
        h.assertEqual(out[0].revs, 200, 'later submission kept');
    });

    h.test('normalizeRows sorts by date ascending', () => {
        const out = Stats.normalizeRows([
            { timestamp: '2026-01-06T14:00:00Z', revs: 2, date: '' },
            { timestamp: '2026-01-04T14:00:00Z', revs: 1, date: '' }
        ], 1);
        h.assertEqual(out[0].revs, 1, 'earlier date first');
        h.assertEqual(out[1].revs, 2, 'later date second');
    });

    h.test('normalizeRows skips blank and junk rows', () => {
        const out = Stats.normalizeRows([
            { timestamp: '2026-01-05T14:00:00Z', revs: '', date: '' },
            { timestamp: 'not a date', revs: 100, date: '' },
            { timestamp: '2026-01-06T14:00:00Z', revs: 100, date: '' }
        ], 1);
        h.assertEqual(out.length, 1, 'only the valid row survives');
    });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node tests.js`
Expected: FAIL — `Stats.milesPerRev is not a function` etc.

- [ ] **Step 3: Implement in `stats.js`** (before the `return`, and add both names to the returned object)

```javascript
    // Distance per wheel revolution for a pet: explicit calibration override,
    // else derived from the wheel diameter (63360 inches per mile).
    function milesPerRev(pet) {
        if (pet.milesPerRev) return pet.milesPerRev;
        return Math.PI * pet.wheelDiameterInches / 63360;
    }

    // Raw endpoint rows {timestamp, revs, date} -> [{date, revs, distance}].
    // The recorded date is the morning the wheel was read (the submission's
    // date) unless the optional date field overrides it. Duplicate dates keep
    // the last submission, so resubmitting corrects a typo.
    function normalizeRows(rows, perRev) {
        const byDate = new Map();
        rows.forEach(row => {
            const revs = Number(row.revs);
            if (row.revs === '' || row.revs === null || !isFinite(revs)) return;
            const raw = row.date ? row.date : row.timestamp;
            const d = new Date(raw);
            if (isNaN(d.getTime())) return;
            const key = d.toLocaleDateString('en-US');
            byDate.set(key, { date: key, revs: revs, distance: revs * perRev });
        });
        return [...byDate.values()].sort((a, b) => new Date(a.date) - new Date(b.date));
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node tests.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add stats.js tests/unit_tests.js
```

```bash
git commit -m "Add normalizeRows and milesPerRev for the form-based pipeline"
```

---

### Task 3: Backend migration — form, tabs, Apps Script, Noodle backfill

**HUMAN CHECKPOINT:** every Google-UI step here is Brad's; the executor prepares the code/instructions, waits, then runs the verification. Nothing in later tasks works against the live pipeline until this completes.

**Files:**
- Create: none in the repo (Apps Script code lives in Google; verification script goes in the session scratchpad, not committed)

**Interfaces:**
- Produces: a live Apps Script deployment URL (call it `NEW_DATA_URL`) serving `GET ?pet=noodle` → `[{timestamp, revs, date}]`; a `noodle` tab in the master spreadsheet with backfilled history; Noodle's calibration numbers (`wheelDiameterInches` rounded for humans, exact `milesPerRev` override) for Task 4's `pets.json`.

- [ ] **Step 1 (Brad): Create Noodle's Google Form**

In Google Forms, create "Noodle — Log a Run" with exactly two questions, in this order (order determines response-tab column order):
1. **Wheel revolutions** — Short answer; Response validation: Number, Greater than or equal to 0; Required.
2. **Date** — Date; not required; description: "Only if this isn't for this morning's reading."

Then Responses → Link to Sheets → **Select existing spreadsheet** → the current Noodle Meter spreadsheet (`1AkG8AGDzFvb4OnOU2qTY3FrM3lkKCM0WOeHSLyX_tNE`).

- [ ] **Step 2 (Brad): Rename the response tab to `noodle`**

In the spreadsheet, rename the new "Form Responses 1" tab to exactly `noodle`. Verify its header row reads `Timestamp | Wheel revolutions | Date`.

- [ ] **Step 3 (Brad): Backfill Noodle's history into the `noodle` tab**

In the old data tab, build three helper columns mirroring history into the response-tab shape — Timestamp = `Date Checked`, Revs = `Revs`, Date = blank — then copy-paste-values them into the `noodle` tab starting at row 2. (Pasting rows into a form-response tab is fine; they sit alongside future submissions.) Spot-check: row count matches the old tab, first and last dates match.

- [ ] **Step 4 (Brad): Replace the Apps Script code and deploy**

Extensions → Apps Script; replace the existing `doGet` with:

```javascript
function doGet(e) {
  var pet = e && e.parameter && e.parameter.pet;
  var result = [];
  if (pet) {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(pet);
    if (sheet) {
      var data = sheet.getDataRange().getValues();
      for (var i = 1; i < data.length; i++) {
        if (data[i][1] === '' || data[i][1] === null) continue;
        result.push({
          timestamp: data[i][0],
          revs: data[i][1],
          date: data[i][2] || ''
        });
      }
    }
  }
  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}
```

Deploy → **New deployment** → Web app → Execute as **Me**, access **Anyone**. Record the new URL (`NEW_DATA_URL`). The old deployment stays live so the production page keeps working until Task 5 ships.

- [ ] **Step 5: Write the verification script to the scratchpad** (not committed)

Save as `<scratchpad>/verify_migration.js`, filling in `NEW_DATA_URL`:

```javascript
// Throwaway migration verifier: compares old endpoint vs new normalized data.
const Stats = require('C:/Users/bradl/SW/noodle_meter/stats.js');

const OLD_URL = 'https://script.google.com/macros/s/AKfycbxoKRMGYPQAxMCUerc8ZO2MPxJl_aeTZRwIzMYej86asddpN4IzkjgOggQMnLtKUCIzuQ/exec';
const NEW_URL = '<NEW_DATA_URL>?pet=noodle';

async function getJson(url) {
    const res = await fetch(url, { redirect: 'follow' });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return res.json();
}

(async () => {
    const oldRows = await getJson(OLD_URL);
    const newRows = await getJson(NEW_URL);

    // Calibration: median distance/revs ratio from the old data.
    const ratios = oldRows.filter(r => Number(r.revs) > 0)
        .map(r => Number(r.distance) / Number(r.revs))
        .sort((a, b) => a - b);
    const perRev = ratios[Math.floor(ratios.length / 2)];
    console.log(`milesPerRev (median old ratio): ${perRev}`);
    console.log(`implied wheelDiameterInches:    ${(perRev * 63360 / Math.PI).toFixed(2)}`);

    const normalized = Stats.normalizeRows(newRows, perRev);
    console.log(`old rows: ${oldRows.length}, new normalized rows: ${normalized.length}`);

    const oldTotal = oldRows.reduce((s, r) => s + Number(r.distance), 0);
    const newTotal = normalized.reduce((s, r) => s + r.distance, 0);
    console.log(`old total: ${oldTotal.toFixed(2)} mi, new total: ${newTotal.toFixed(2)} mi`);

    const oldByDate = new Map(oldRows.map(r =>
        [new Date(r.date).toLocaleDateString('en-US'), Number(r.distance)]));
    let mismatches = 0;
    normalized.forEach(r => {
        const oldDist = oldByDate.get(r.date);
        if (oldDist === undefined || Math.abs(oldDist - r.distance) > 0.05) {
            console.log(`MISMATCH ${r.date}: old=${oldDist}, new=${r.distance.toFixed(3)}`);
            mismatches++;
        }
    });
    console.log(mismatches === 0 ? 'PASS: all dates match within rounding'
        : `FAIL: ${mismatches} mismatched dates`);
})();
```

- [ ] **Step 6: Run the verifier**

Run: `node <scratchpad>/verify_migration.js`
Expected: row counts equal, totals within a mile of each other, `PASS: all dates match within rounding`. Record the printed `milesPerRev` and `wheelDiameterInches` for Task 4. If it fails, fix the backfill (Step 3) before proceeding.

- [ ] **Step 7 (Brad): Smoke-test a real form submission**

Submit a test count via the form; re-run the verifier or curl `NEW_DATA_URL?pet=noodle` and confirm the row appears with a timestamp. Delete the test row from the `noodle` tab afterwards.

No commit — this task changes nothing in the repo.

---

### Task 4: `pets.json`, image move, schema tests

**Files:**
- Create: `pets.json`
- Create: `tests/schema_tests.js`
- Modify: `tests.js` (register the schema suite)
- Modify: `index.html` (image path only — one line, keeps the live page working)
- Rename: `noodle_cropped.jpg` → `images/noodle.jpg` (via `git mv`)

**Interfaces:**
- Consumes: `NEW_DATA_URL`, calibration numbers from Task 3.
- Produces: `pets.json` with shape `{dataUrl, pets: [{slug, name, title, image, wheelDiameterInches, milesPerRev, formUrl}]}` — Task 5's frontend and Task 6's endpoint tests read this file (browser fetch and Node `require` respectively).

- [ ] **Step 1: Move the image**

```bash
mkdir -p images
```

```bash
git mv noodle_cropped.jpg images/noodle.jpg
```

Update the `<img>` in `index.html`: `src="noodle_cropped.jpg"` → `src="images/noodle.jpg"`.

- [ ] **Step 2: Write failing schema tests in `tests/schema_tests.js`**

```javascript
// Schema tests: pets.json is well-formed and internally consistent.
const fs = require('fs');
const path = require('path');
const Stats = require('../stats.js');

async function run(h) {
    console.log('\nSchema tests (pets.json)');

    let config;
    h.test('pets.json parses', () => {
        config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'pets.json'), 'utf8'));
    });
    if (!config) return;

    h.test('dataUrl is an https URL', () => {
        h.assertTrue(typeof config.dataUrl === 'string' &&
            config.dataUrl.startsWith('https://'), `bad dataUrl: ${config.dataUrl}`);
    });

    h.test('pets is a non-empty array', () => {
        h.assertTrue(Array.isArray(config.pets) && config.pets.length > 0, 'pets array');
    });

    h.test('slugs are well-formed and unique', () => {
        const slugs = config.pets.map(p => p.slug);
        slugs.forEach(s => h.assertTrue(/^[a-z0-9_-]+$/.test(s), `bad slug: ${s}`));
        h.assertEqual(new Set(slugs).size, slugs.length, 'unique slugs');
    });

    config.pets.forEach(pet => {
        h.test(`pet '${pet.slug}' has name, title, formUrl`, () => {
            h.assertTrue(typeof pet.name === 'string' && pet.name.length > 0, 'name');
            h.assertTrue(typeof pet.title === 'string' && pet.title.length > 0, 'title');
            h.assertTrue(typeof pet.formUrl === 'string' &&
                pet.formUrl.startsWith('https://'), 'formUrl');
        });
        h.test(`pet '${pet.slug}' image file exists`, () => {
            h.assertTrue(fs.existsSync(path.join(__dirname, '..', pet.image)),
                `missing ${pet.image}`);
        });
        h.test(`pet '${pet.slug}' has a positive milesPerRev`, () => {
            const perRev = Stats.milesPerRev(pet);
            h.assertTrue(isFinite(perRev) && perRev > 0, `milesPerRev = ${perRev}`);
        });
    });
}

module.exports = { run };
```

Register it in `tests.js` after the unit suite:

```javascript
    await require('./tests/schema_tests').run(harness);
```

- [ ] **Step 3: Run tests to verify the schema suite fails**

Run: `node tests.js`
Expected: FAIL — `pets.json` missing.

- [ ] **Step 4: Create `pets.json`**

Fill in the real values from Task 3 (`<NEW_DATA_URL>`, the form's share link, the recorded calibration; `milesPerRev` is the exact median ratio, `wheelDiameterInches` the rounded human-readable equivalent):

```json
{
  "dataUrl": "<NEW_DATA_URL>",
  "pets": [
    {
      "slug": "noodle",
      "name": "Noodle",
      "title": "Noodle's Running Tracker",
      "image": "images/noodle.jpg",
      "wheelDiameterInches": 8.3,
      "milesPerRev": 0.0000123456789,
      "formUrl": "<NOODLE_FORM_SHARE_URL>"
    }
  ]
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node tests.js`
Expected: PASS (schema suite green; old endpoint suite still green).

- [ ] **Step 6: Commit**

```bash
git add pets.json tests/schema_tests.js tests.js index.html images/noodle.jpg
```

```bash
git commit -m "Add pets.json config with schema tests; move photo to images/"
```

---

### Task 5: Frontend multi-pet cutover

Rewrites the page's data layer around `pets.json` + the new endpoint, and adds the switcher, per-pet header, form link, and empty state. After this task the page no longer uses the old endpoint.

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `pets.json` (Task 4), `Stats.normalizeRows` / `Stats.milesPerRev` (Task 2), live `?pet=` endpoint (Task 3).
- Produces: URL contract `index.html?pet=<slug>`; localStorage keys `noodle_meter_last_pet` and `noodle_meter_cache_<slug>`.

- [ ] **Step 1: Update the static HTML**

Replace the header block inside `.container`:

```html
        <button class="view-toggle" id="view-toggle" title="Toggle stats view">&#x1F4CA;</button>
        <a class="form-link" id="form-link" target="_blank" rel="noopener" title="Log this morning's count">&#x270F;&#xFE0F;</a>
        <h1 class="page-title" id="page-title"></h1>
        <select class="pet-select" id="pet-select"></select>
        <img src="images/noodle.jpg" alt="" class="hamster-image" id="pet-image">
```

Add CSS (near `.view-toggle`):

```css
        .form-link {
            position: absolute;
            top: 0;
            right: 0;
            background: rgba(255,255,255,0.9);
            border: none;
            width: 44px;
            height: 44px;
            border-radius: 50%;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            font-size: 1.2rem;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
        }

        .form-link:hover {
            background: #fff;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: scale(1.05);
        }

        .pet-select {
            margin: -10px auto 20px;
            display: block;
            padding: 6px 12px;
            border-radius: 16px;
            border: 1px solid #ccc;
            background: rgba(255,255,255,0.9);
            font-size: 0.9rem;
            color: #2c3e50;
            cursor: pointer;
        }

        .empty-state {
            font-size: 1.2rem;
            color: #555;
            margin-top: 50px;
            line-height: 2;
        }
```

- [ ] **Step 2: Replace the data-layer script**

In the inline script, remove the `DATA_URL` constant and the `CACHE_KEY` constant, and replace `loadFromCache`, `saveToCache`, `fetchData`, and the `// Initialize` call with:

```javascript
        const CONFIG_URL = 'pets.json';
        const LAST_PET_KEY = 'noodle_meter_last_pet';

        let config = null;
        let currentPet = null;

        function cacheKey() {
            return `noodle_meter_cache_${currentPet.slug}`;
        }

        function loadFromCache() {
            try {
                const cached = localStorage.getItem(cacheKey());
                if (!cached) return null;
                const { data: cachedData, cachedAt } = JSON.parse(cached);
                if (cachedAt === getTodayString() && hasTodayData(cachedData)) {
                    return cachedData;
                }
            } catch (e) {
                console.warn('Cache read failed:', e);
            }
            return null;
        }

        function saveToCache(dataArray) {
            if (!hasTodayData(dataArray)) {
                console.log('Not caching - no data for today yet');
                return;
            }
            try {
                localStorage.setItem(cacheKey(), JSON.stringify({
                    data: dataArray,
                    cachedAt: getTodayString()
                }));
            } catch (e) {
                console.warn('Cache write failed:', e);
            }
        }

        function resolvePetSlug() {
            const param = new URLSearchParams(location.search).get('pet');
            if (config.pets.some(p => p.slug === param)) return param;
            const last = localStorage.getItem(LAST_PET_KEY);
            if (config.pets.some(p => p.slug === last)) return last;
            return config.pets[0].slug;
        }

        function buildPetSelect() {
            const select = document.getElementById('pet-select');
            if (config.pets.length < 2) {
                select.style.display = 'none';
                return;
            }
            select.innerHTML = config.pets.map(p =>
                `<option value="${p.slug}">${p.name}</option>`).join('');
            select.addEventListener('change', () => switchPet(select.value));
        }

        function switchPet(slug) {
            currentPet = config.pets.find(p => p.slug === slug);
            localStorage.setItem(LAST_PET_KEY, slug);
            const url = new URL(location);
            url.searchParams.set('pet', slug);
            history.replaceState(null, '', url);

            document.title = currentPet.title;
            document.getElementById('page-title').textContent = currentPet.title;
            const img = document.getElementById('pet-image');
            img.src = currentPet.image;
            img.alt = currentPet.name;
            document.getElementById('form-link').href = currentPet.formUrl;
            document.getElementById('pet-select').value = slug;

            data = [];
            currentIndex = 0;
            document.getElementById('prev-btn').disabled = true;
            document.getElementById('next-btn').disabled = true;
            document.getElementById('content').innerHTML =
                '<div class="loading"><div class="spinner"></div></div>';
            fetchData();
        }

        function showEmptyState() {
            document.getElementById('content').innerHTML = `
                <div class="empty-state">No runs logged yet.<br>
                <a href="${currentPet.formUrl}" target="_blank" rel="noopener">Log the first one!</a></div>
            `;
        }

        async function fetchData() {
            const slug = currentPet.slug;
            const cachedData = loadFromCache();
            if (cachedData) {
                console.log('Using cached data');
                processData(cachedData);
                return;
            }

            try {
                const response = await fetch(`${config.dataUrl}?pet=${encodeURIComponent(slug)}`);
                if (!response.ok) throw new Error('Failed to fetch data');
                const rows = await response.json();
                if (currentPet.slug !== slug) return; // user switched pets mid-fetch

                const processedData = Stats.normalizeRows(rows, Stats.milesPerRev(currentPet));
                if (processedData.length === 0) {
                    showEmptyState();
                    return;
                }

                saveToCache(processedData);
                processData(processedData);
            } catch (error) {
                if (currentPet.slug !== slug) return;
                showError('Could not load data. Please check that the spreadsheet is public.');
                console.error(error);
            }
        }

        async function init() {
            try {
                const resp = await fetch(CONFIG_URL);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                config = await resp.json();
            } catch (e) {
                showError('Could not load pets.json');
                console.error(e);
                return;
            }
            buildPetSelect();
            switchPet(resolvePetSlug());
        }

        // Initialize
        init();
```

- [ ] **Step 3: Preserve the view across pet switches**

At the end of `processData`, replace `updateDisplay();` with:

```javascript
            if (currentView === 'stats') {
                showStatsView();
            } else {
                updateDisplay();
            }
```

- [ ] **Step 4: Scope the cache-clear shortcut to the current pet**

In the Ctrl+Shift+R keydown handler, replace `localStorage.removeItem(CACHE_KEY);` with `localStorage.removeItem(cacheKey());`.

- [ ] **Step 5: Run the automated tests**

Run: `node tests.js`
Expected: PASS (nothing in the suites depends on index.html; this catches accidental damage to stats.js/pets.json).

- [ ] **Step 6: Verify in the browser against the live pipeline**

Run: `C:/Python314/python.exe -m http.server 8000` (background), open `http://localhost:8000/`.
Expected checks:
- Loads Noodle by default; title "Noodle's Running Tracker"; photo renders; URL rewritten to `?pet=noodle`.
- Today's/latest distance matches the old production page's value.
- Stats view: total miles ≈ old page's total; histogram and activity grid render.
- Pencil link opens Noodle's form in a new tab.
- Pet dropdown is hidden (single pet).
- `?pet=nonexistent` falls back to Noodle; no console errors.
Kill the server afterwards.

- [ ] **Step 7: Commit**

```bash
git add index.html
```

```bash
git commit -m "Cut the page over to per-pet config, forms pipeline, and pet switcher"
```

---

### Task 6: Endpoint tests for the new contract

**Files:**
- Modify: `tests/endpoint_tests.js` (full rewrite)

**Interfaces:**
- Consumes: `pets.json` via `require('../pets.json')`; live endpoint from Task 3; `Stats.normalizeRows`/`Stats.milesPerRev`.

- [ ] **Step 1: Rewrite `tests/endpoint_tests.js`**

```javascript
// Endpoint tests: every pet in pets.json is served by the live Apps Script.
const https = require('https');
const Stats = require('../stats.js');
const config = require('../pets.json');

function fetchUrl(url) {
    return new Promise((resolve, reject) => {
        const makeRequest = (url) => {
            https.get(url, (res) => {
                if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    makeRequest(res.headers.location);
                    return;
                }
                if (res.statusCode !== 200) {
                    reject(new Error(`HTTP ${res.statusCode}`));
                    return;
                }
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => resolve({ data, status: res.statusCode }));
            }).on('error', reject);
        };
        makeRequest(url);
    });
}

async function run(h) {
    console.log('\nEndpoint tests');

    for (const pet of config.pets) {
        let rows;
        try {
            const response = await fetchUrl(`${config.dataUrl}?pet=${encodeURIComponent(pet.slug)}`);
            rows = JSON.parse(response.data);
        } catch (error) {
            h.test(`'${pet.slug}' endpoint responds with valid JSON`, () => { throw error; });
            continue;
        }
        h.test(`'${pet.slug}' endpoint responds with valid JSON`, () => {
            h.assertTrue(Array.isArray(rows), 'response is an array');
        });
        h.test(`'${pet.slug}' rows have timestamp and revs fields`, () => {
            rows.forEach((row, i) => {
                h.assertTrue('timestamp' in row, `row ${i}: missing timestamp`);
                h.assertTrue('revs' in row, `row ${i}: missing revs`);
                h.assertTrue('date' in row, `row ${i}: missing date`);
            });
        });
        h.test(`'${pet.slug}' normalized distances are reasonable (0-50 mi)`, () => {
            const normalized = Stats.normalizeRows(rows, Stats.milesPerRev(pet));
            normalized.forEach(r => {
                h.assertTrue(r.distance >= 0 && r.distance <= 50,
                    `${r.date}: distance ${r.distance} out of range`);
            });
        });
    }

    let unknownRows = null;
    let unknownError = null;
    try {
        const response = await fetchUrl(`${config.dataUrl}?pet=no_such_pet_xyz`);
        unknownRows = JSON.parse(response.data);
    } catch (error) {
        unknownError = error;
    }
    h.test('unknown pet slug returns an empty array', () => {
        if (unknownError) throw unknownError;
        h.assertTrue(Array.isArray(unknownRows) && unknownRows.length === 0,
            `expected [], got ${JSON.stringify(unknownRows).slice(0, 80)}`);
    });
}

module.exports = { run };
```

- [ ] **Step 2: Run the full suite**

Run: `node tests.js`
Expected: PASS — unit, schema, and new endpoint suites all green against the live deployment.

- [ ] **Step 3: Commit**

```bash
git add tests/endpoint_tests.js
```

```bash
git commit -m "Test the per-pet endpoint contract for every configured pet"
```

---

### Task 7: Point the analysis script at the new endpoint

The photoperiod model works entirely in revolutions (wheel calibration never enters it), so only its fetch/normalize layer changes.

**Files:**
- Modify: `analysis/photoperiod_model.py` (the `DATA_URL` constant near line 27 and the `load()` function near line 117)

**Interfaces:**
- Consumes: `NEW_DATA_URL` from Task 3 (read it from `pets.json` manually; the script keeps its own constant, as today).

- [ ] **Step 1: Update `DATA_URL`**

Replace the old deployment URL with `<NEW_DATA_URL>?pet=noodle` (keep the existing split-string formatting style).

- [ ] **Step 2: Replace `load()` with the new-contract normalizer**

Same semantics as `Stats.normalizeRows`, minus distance (the model uses revs): effective date = override if present else timestamp, last submission wins per date.

```python
def load():
    with urllib.request.urlopen(DATA_URL) as r:
        raw = json.load(r)
    by_date = {}
    for x in raw:
        if x.get("revs") in ("", None):
            continue
        src = x["date"] or x["timestamp"]
        d = to_local(datetime.fromisoformat(str(src).replace("Z", "+00:00"))).date()
        by_date[d] = float(x["revs"])  # last submission wins
    rows = sorted(by_date.items())
    return [r[0] for r in rows], np.array([r[1] for r in rows])
```

- [ ] **Step 3: Verify the model reproduces its results**

Run: `C:/Python314/python.exe analysis/photoperiod_model.py`
Expected: runs to completion; the reported photoperiod share of the decline matches the committed write-up (~85%) — the backfilled data is the same nights, so results should be identical to within noise. Compare the regenerated `analysis/report.html` numbers against the committed version before staging it.

- [ ] **Step 4: Commit**

```bash
git add analysis/photoperiod_model.py analysis/report.html
```

```bash
git commit -m "Read the analysis data from the per-pet endpoint"
```

---

### Task 8: Documentation and old-tab retirement

**Files:**
- Modify: `README.md`
- Modify: `IMPLEMENTATION.md`

- [ ] **Step 1: Update `README.md`**

Retitle the About section around multiple pets: data captured per pet with a wheel pedometer, submitted via each pet's Google Form, displayed at `?pet=<slug>`. Keep the Noodle analysis section (note it's Noodle-specific). Keep the live-site link.

- [ ] **Step 2: Update `IMPLEMENTATION.md`**

- Architecture diagram becomes the four-stage pipeline (Forms → master spreadsheet tab-per-pet → Apps Script `?pet=` → GitHub Pages + pets.json), matching the spec.
- Replace the Apps Script section's code with the Task 3 `doGet` and note that slug = tab name so new pets never touch the script.
- Add a **pets.json reference** table (field, meaning, example) including the `milesPerRev` override rule.
- Add the **add-a-pet runbook**: create form (two questions, revolutions first) → link to master sheet → rename response tab to slug → add photo to `images/` + entry to `pets.json` → commit. Share the form link with the pet's owners; grant spreadsheet edit access only to people who need to fix typos.
- Document date semantics: recorded date = the morning the wheel is read; optional Date question overrides for backfill; duplicate dates resolve last-submission-wins.
- Update Local Files table (`stats.js`, `pets.json`, `tests/`, `images/`) and the Testing section (three suites, still `node tests.js`).
- Update Troubleshooting: per-pet cache keys (`noodle_meter_cache_<slug>`), config now in `pets.json` (not an index.html constant), new-deployment steps update `pets.json`.

- [ ] **Step 3 (Brad): Retire the old data tab and deployment**

After a few days of the new pipeline running clean: archive/delete the old data tab in the spreadsheet and the old Apps Script deployment. (Deliberately deferred; nothing in the repo references them after Task 5.)

- [ ] **Step 4: Run tests**

Run: `node tests.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md IMPLEMENTATION.md
```

```bash
git commit -m "Document the multi-pet architecture and add-a-pet runbook"
```
