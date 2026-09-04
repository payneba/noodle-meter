# Noodle Meter - Implementation Details

## Overview

A web app that tracks daily running distances for hamsters (and whatever else
ends up on a wheel). Displays distance data with visual effects based on
performance tiers. Started single-pet (Noodle); now supports multiple pets,
each with its own submission form, wheel size, and photo, all served from one
deployment.

## Architecture

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐     ┌───────────────┐
│ Google Form  │ ──► │  Master Spreadsheet │ ──► │ Apps Script  │ ──► │ GitHub Pages  │
│ (one / pet)  │     │  (one tab / pet)    │     │ ?pet=<slug>  │     │ (web app)     │
└──────────────┘     └─────────────────────┘     └──────────────┘     └───────────────┘
                                                                        + pets.json (config)
```

All computation happens client-side ("thin server, smart client"): the Apps
Script deployment serves raw rows for whichever pet is requested; distance
calculation, deduplication, tier grading, and stats are computed in the
browser from `pets.json`. That keeps the Apps Script untouched when pets are
added or removed, and keeps the logic in git — versioned and unit-tested.

## External Dependencies

### 1. Master Spreadsheet

- **Purpose**: Primary data store for every pet's daily running stats. One
  spreadsheet, one response tab per pet.
- **Tab naming**: each tab's name **is** the pet's slug (e.g. `noodle`). The
  Apps Script looks up the tab by that name, so renaming a tab breaks the
  pet's data feed.
- **Tab columns** (written by the pet's linked Google Form): `Timestamp | Revs | Date`
  — `Date` is the optional override question and is usually blank.
- **Access**: sheet must stay shared as "Anyone with the link can view" (the
  Apps Script and the public site depend on it). Owners who need to fix a
  typo get spreadsheet edit access directly; this is friends-and-family
  scale, so per-tab permission isolation is out of scope.

### 2. Google Apps Script

- **Purpose**: serves one pet's tab as JSON, keyed by a `pet` query parameter,
  with CORS headers (bypasses browser restrictions).
- **Deployment URL**: lives in `pets.json` (`dataUrl`), not hardcoded in
  `index.html` — see the pets.json reference below.
- **Bound to**: the master spreadsheet above.

#### Apps Script Code

To recreate, go to the master spreadsheet → Extensions → Apps Script, and set:

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

`getSheetByName(pet)` is why slug = tab name: **adding a pet never touches
this script.** An unknown slug or an empty/missing tab returns `[]`, never an
error — the app renders a "no runs logged yet" empty state instead of
breaking.

#### Deployment Settings

- Deploy → New deployment → Web app
- Execute as: **Me**
- Who has access: **Anyone**

After deploying, copy the web app URL into `pets.json`'s `dataUrl` field (not
`index.html` — the app has no per-pet or per-deployment constants baked in).
Editing the Apps Script code always requires a **new** deployment; the URL
changes each time, so `pets.json` needs updating too.

### 3. GitHub Pages

- **Repository**: https://github.com/payneba/noodle-meter
- **Pages URL**: https://payneba.github.io/noodle-meter/
- **Branch**: `main`
- **Settings**: Settings → Pages → Deploy from branch → main / root

## Configuration: `pets.json`

Repo-root file, fetched once before the first data request. One `dataUrl`
(shared by all pets, since it's one Apps Script deployment) plus a `pets`
array:

| Field | Meaning | Example |
|---|---|---|
| `dataUrl` | The Apps Script `/exec` URL (top-level, not per-pet) | `https://script.google.com/macros/s/…/exec` |
| `slug` | Lowercase identifier; **must match the spreadsheet tab name**; used in `?pet=<slug>` | `"noodle"` |
| `name` | Short display name (dropdown entries, image alt text) | `"Noodle"` |
| `title` | Free-form page title/heading — no required pattern | `"Noodle's Running Tracker"` |
| `image` | Path to the pet's photo, under `images/` | `"images/noodle.jpg"` |
| `wheelDiameterInches` | Wheel diameter; distance = `revs × π × diameter / 63360` | `8` |
| `milesPerRev` | *Optional.* Overrides the diameter-derived value for an oddly calibrated pedometer | `0.00042` |
| `formUrl` | The pet's Google Form share link (shown in the empty state; owners bookmark it directly) | `https://forms.gle/…` |

`milesPerRev` beats `wheelDiameterInches` when both are present — set it only
if a pet's actual distance-per-rev doesn't match a clean diameter figure.

## Date semantics

The recorded date for a submission is **the morning the wheel is read** (i.e.
the date the owner submits the form), matching the pedometer routine: reset
the wheel, run overnight, read and submit the next morning. The form's
optional **Date** question overrides this — use it for backfill or a late
entry, when the submission date isn't the reading's date.

Duplicate dates (e.g. a corrected resubmission) resolve by **latest
timestamp**, not sheet row order. A form linked to the sheet inserts each new
response directly below the last form-written row — *above* any manually
pasted backfill — so row position carries no ordering information. The app
sorts and deduplicates by timestamp itself.

## Add-a-pet runbook

No script or code changes are needed to add a pet — only a form, a tab
rename, and a `pets.json` entry.

1. **Create a Google Form** with exactly two questions, in this order:
   - **Wheel revolutions** — short answer, number validation (≥ 0), required.
   - **Date** — date field, optional, description "Only if this isn't for
     this morning's reading".
2. **Responses → Link to Sheets → Select existing spreadsheet** → choose the
   master spreadsheet.
3. **Rename the new response tab** to the pet's slug (lowercase, matches what
   goes in `pets.json`).
4. **Publish the form** and copy the responder link (current Forms UI:
   **Publish** button, top right, then copy the link; older UI: **Send** →
   link icon). Share that link with the pet's owners — it's the entire
   submission workflow *and* the access gate. Submitters need no spreadsheet
   access at all.
5. **Add a photo** to `images/<slug>.jpg` and an entry to `pets.json`. Run
   `node tests.js` to confirm the schema and endpoint checks pass, then
   commit.

The pet's page is live at `?pet=<slug>`. The header pet-switcher dropdown
appears automatically once there are 2+ pets configured (a single pet renders
as plain text, no dropdown). A newly added pet with no submissions yet shows
an empty state with a link to its form rather than an error.

Grant spreadsheet edit access only to whoever needs to fix a typo directly in
the sheet; everyone else only ever touches the form.

### Corrections

- **Same-day fix**: resubmit the form — the latest timestamp wins, so a
  resubmission on the same date silently corrects the earlier one.
- **Sheet-level fix**: someone with spreadsheet edit access can edit the row
  directly.

## Local Files

| File | Purpose |
|------|---------|
| `index.html` | Page structure and DOM/rendering logic; loads `pets.json` and `stats.js` |
| `stats.js` | Pure computation (dedup, distance, tiers, thresholds) — UMD module, unit-tested, no DOM |
| `pets.json` | Per-pet configuration (see above) |
| `images/` | Pet photos, one per slug (e.g. `images/noodle.jpg`) |
| `tests.js` | Entry point that runs all three test suites |
| `tests/harness.js` | Minimal test runner used by the suites |
| `tests/unit_tests.js` | Unit tests for `stats.js` (offline) |
| `tests/schema_tests.js` | Validates `pets.json` (offline) |
| `tests/endpoint_tests.js` | Live per-pet contract checks against the Apps Script endpoint (needs network) |
| `analysis/` | Noodle-specific photoperiod model and report (`?pet=noodle`) |
| `.github/workflows/test.yml` | GitHub Actions workflow, runs `node tests.js` on push/PR |

## Features

### Visual Tiers (based on recent form)

Tiers are graded against the **trailing 30 days** (`TIER_WINDOW_DAYS`), not all-time.

| Tier | Condition | Color | Effects |
|------|-----------|-------|---------|
| Low | Below 25th percentile of last 30 days | Blue | Smaller text |
| Medium | 25th-75th percentile of last 30 days | Green | Normal text |
| High | Above 75th percentile of last 30 days | Orange | Larger text, glow |
| Record | Highest ever (all-time) | Red | Largest text, pulse animation, confetti |

A "High" night that also beats every night in the trailing window earns the
**Best in a Month!** badge.

#### Why a trailing window, not all-time percentiles

Noodle runs at night, from lights-out to sunrise. In Andover MA the dark window
runs ~9.1h in January but only ~7.1h at the summer solstice, and she does roughly
4,500 revolutions per hour of darkness — so a summer night yields ~9,000 fewer revs
than a winter one for no reason other than the calendar.

Grading against all-time percentiles therefore measured the season, not the hamster:
by June/July **0%** of nights could reach the "High" tier, 60% were stuck at "Low",
and the all-time Record was unbeatable until winter. The trailing window slides with
the daylight, so a good night reads as good year-round (Jun/Jul went from 0 to 7
celebration nights on the same data). Record stays all-time — it's the rare prize,
and it will come back into reach as the nights lengthen.

Analysis note: with data through early September, the long-run decline is mostly
photoperiod (~86%), but the residual "she's slowing down" trend is now small and
statistically significant (−30 ± 5 revs/day) on top of it. This tiering rationale —
grade against recent form, not the season — is unaffected either way.
Full derivation and the script that reproduces it: [analysis/README.md](analysis/README.md).
**Note:** that write-up is a snapshot through 2026-07-13 (173 nights) and predates
this update — with data through 2026-09-04 the residual-trend conclusion flipped
from not-significant to significant (see above); re-run
`analysis/photoperiod_model.py` for current numbers.

### Histogram

Scoped to the last 90 days (`HISTOGRAM_WINDOW_DAYS`) and coloured against that
window's own thresholds. Pooling all history mixes long winter nights with short
summer ones — two populations several miles apart — which smears the distribution
into a shapeless lump. Red is reserved for the all-time record, so the top bucket
only turns red if the record day falls inside the window.

### Pet switching

- **URL scheme**: `?pet=<slug>`. Resolution order: URL param → last-viewed
  pet (`localStorage`, key `noodle_meter_last_pet`) → first pet in
  `pets.json`. Switching pets rewrites the URL, so every pet has a shareable
  link.
- **Switcher**: a dropdown in the header, present on both the home and stats
  views. With exactly one pet configured it renders as plain text.
- Switching pets refetches (or hits that pet's cache), recomputes tiers, and
  resets to the latest entry; the current view (home/stats) is preserved.

### Caching

- Uses `localStorage` to cache data, one entry per pet: key
  `noodle_meter_cache_<slug>`.
- Cache is valid only if:
  - Cached today
  - Contains today's data
- If today's data not in sheet yet, cache is skipped (ensures fresh fetch)
- `Ctrl+Shift+R` clears the **current pet's** cache and reloads (other pets'
  caches are untouched).

## Testing

Run tests locally (requires Node.js):

```bash
node tests.js
```

This runs three suites:

1. **Unit tests** (`tests/unit_tests.js`) — `stats.js` logic: dedup/latest-wins,
   date-override handling, distance calculation, tier/threshold edge cases.
   Offline, no network needed.
2. **Schema tests** (`tests/schema_tests.js`) — validates `pets.json`: required
   fields present, slugs unique, image files exist on disk, each pet has a
   usable `wheelDiameterInches` and/or `milesPerRev`. Offline.
3. **Endpoint tests** (`tests/endpoint_tests.js`) — for each pet in
   `pets.json`, fetches `dataUrl?pet=<slug>` and validates the JSON array
   shape and value ranges. Needs network.

GitHub Actions (`.github/workflows/test.yml`) runs the full suite on every
push and pull request.

## Troubleshooting

### "Could not load data" error

1. Check that `pets.json`'s `dataUrl` matches the **current** Apps Script
   deployment (a new deployment gets a new URL).
2. Verify the sheet is still shared "Anyone with the link can view".
3. Check browser console for specific error messages.

### Data not updating for one pet

1. Confirm the pet's spreadsheet tab name matches its `slug` in `pets.json`
   exactly (the Apps Script looks the tab up by that name).
2. Clear that pet's cache: open the pet's page and press `Ctrl+Shift+R`, or
   run `localStorage.removeItem('noodle_meter_cache_<slug>')` in the console.
3. Verify the new row exists in that pet's tab.

### Apps Script changes not reflected

After editing Apps Script code, you must create a **new deployment**:
1. Deploy → New deployment (not "Manage deployments") — this changes the URL.
2. Update `dataUrl` in `pets.json`.
3. Commit and push changes.

## Future Improvements

- [ ] GitHub Actions to cache data as static JSON (faster first load)
- [ ] Historical charts/graphs
- [ ] Weekly/monthly summaries
