# Multi-Pet Support — Design Spec

**Date:** 2026-09-04
**Status:** Approved for planning

## Goal

Extend the app from a single hardcoded pet (Noodle) to multiple pets with
multiple owners. Per-pet: page title, photo, wheel size, submission form, and
running stats. Single-digit pet count; access gated by sharing links, not
logins. Viewing stays public.

## Architecture Overview

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────┐     ┌───────────────┐
│ Google Form  │ ──► │  Master Spreadsheet │ ──► │ Apps Script  │ ──► │ GitHub Pages  │
│ (one / pet)  │     │  (one tab / pet)    │     │ ?pet=<slug>  │     │ (web app)     │
└──────────────┘     └─────────────────────┘     └──────────────┘     └───────────────┘
                                                                        + pets.json (config)
```

Computation lives in the client ("thin server, smart client"): the Apps Script
serves raw rows; distance, dedup, tiers, and stats are computed in the browser
from `pets.json` config. Rationale: logic stays in git (versioned, testable),
the Apps Script is touched only if the serving contract changes, and the wheel
size has exactly one home.

## Data Pipeline

### Google Forms (one per pet)

Two questions:

1. **Wheel revolutions** — short answer, number validation, required.
2. **Date** — date field, optional, labeled "only if this isn't for this
   morning's reading". Blank means the submission's own date.

Owner routine: read the pedometer when the wheel is first ready to read (the
morning after the run), reset it, open the bookmarked form link, submit the
count. The form link is the write-access gate — submitters need nothing else.

### Date semantics

Consistent with today's `Date Checked` column: **the recorded date is the date
the wheel is read, i.e. the morning after the run** — unless the optional Date
field overrides it (for backfill and late entries). Effective date =
date-override if present, else the response timestamp's date.

### Master spreadsheet

The existing spreadsheet becomes the master. Each pet's form is linked to it;
the response tab is renamed to the pet's slug (`noodle`, `pickle`, …).
Response tab columns: `Timestamp | Revs | Date` (override, usually blank).

- Sharing: "Anyone with the link can view" (required by the Apps Script /
  public site, unchanged from today).
- Owners who need to correct typos get edit access to the spreadsheet.
  Friends-and-family scale; per-tab isolation is explicitly out of scope.

### Apps Script

One deployment. `doGet(e)`:

- Reads `e.parameter.pet`, calls `getSheetByName(slug)`.
- Returns raw rows as JSON: `[{timestamp, revs, date}]` (date may be empty).
- Unknown slug or empty tab → empty JSON array (never an error; the client
  renders a friendly "no runs logged yet" state).
- Because slug = tab name, adding a pet never touches the script.

### Client normalization (replaces the sheet's distance formula)

1. Effective date = date-override || timestamp's date.
2. Deduplicate by effective date, **latest timestamp wins** (resubmitting
   corrects a typo). Timestamp order, not sheet-row order: a linked form
   inserts each response directly below the last form-written row — above
   any manually pasted backfill — so row position carries no submission
   ordering. Ties (identical timestamps, e.g. within backfill) keep sheet
   order via stable sort.
3. Sort ascending by date.
4. `distance = revs × milesPerRev` from the pet's config.

## Configuration: `pets.json`

New file in the repo root, fetched before the first data fetch:

```json
{
  "dataUrl": "https://script.google.com/macros/s/…/exec",
  "pets": [
    {
      "slug": "noodle",
      "name": "Noodle",
      "title": "Noodle's Running Tracker",
      "image": "images/noodle.jpg",
      "wheelDiameterInches": 8.3,
      "formUrl": "https://forms.gle/…"
    }
  ]
}
```

- `title` is free-form per pet ("Pickle's Marathon Training") and is used for
  both the page `<title>` and the on-page heading. `name` is the short display
  name (dropdown entries, alt text).
- `milesPerRev = π × wheelDiameterInches / 63360`. Optional per-pet
  `milesPerRev` field overrides the diameter-derived value for oddly
  calibrated pedometers.
- The Apps Script URL lives here (not hardcoded in index.html) so all
  deployment config is in one file.
- Photos live in a new `images/` directory.

## Frontend

- **URL scheme:** `?pet=<slug>`. Resolution order: URL param → last-viewed pet
  (localStorage) → first pet in pets.json. Switching pets rewrites the URL via
  `history.replaceState`, so each pet has a shareable view URL.
- **Pet switcher:** dropdown in the header area, present on both home and
  stats views (it lives outside the swapped `#content` div). With exactly one
  pet configured it renders as plain text — no dropdown until there's a
  choice.
- **Per-pet content:** `<title>` and heading from config `title`; photo from
  config `image`; a "Log this morning's count" link opens the pet's `formUrl`
  in a new tab, making the pet's page the hub owners bookmark.
- **Cache:** localStorage key becomes `noodle_meter_cache_<slug>`; validity
  rules unchanged (cached today + contains today's data).
- **Pet switch behavior:** refetch (or per-pet cache hit), recompute
  thresholds/tiers, reset `currentIndex` to the latest entry; current view
  (home/stats) is preserved.
- **Empty state:** a pet with no data shows "no runs logged yet" plus the
  form link, not an error.
- All existing display logic (trailing-30-day tier grading, histogram,
  activity grid, confetti, navigation, badges) is unchanged; it already
  operates on a `data` array and is simply rebuilt on pet switch.

## Testability Refactor

Extract the pure computation functions from the inline script into `stats.js`,
loaded by `index.html` via `<script src>` and `require`-able from Node
(UMD-style guard): normalization/dedup, percentile, `windowThresholds`,
`trailingDistances`, `computeTiers`, distance calc. The page remains a static
app on GitHub Pages; DOM/rendering code stays in index.html.

## Migration (Noodle)

1. Create Noodle's form; link it to the existing spreadsheet; rename the
   response tab `noodle`.
2. Backfill history into the tab: Timestamp = historical `Date Checked`,
   Revs = revs, Date override blank.
3. Back-derive Noodle's effective wheel diameter (or `milesPerRev`) from the
   existing distance ÷ revs ratio so recomputed history matches the old sheet.
4. Update the Apps Script to the param-based `doGet`; create a new deployment;
   record its URL in `pets.json`.
5. Verify: recomputed per-day distances and total mileage match the old sheet
   within rounding; then retire the old tab.
6. Point `analysis/photoperiod_model.py` at the new endpoint (`?pet=noodle`);
   step 3 keeps its results identical.

### Add-a-pet runbook (goes in IMPLEMENTATION.md)

Create form → link to master sheet → rename response tab to slug → add photo
to `images/` and entry to `pets.json` → commit. No script or code changes.

## Testing

`tests.js` grows three groups (run by the existing GitHub Actions workflow):

1. **pets.json schema:** required fields present, slugs unique, image files
   exist on disk, each pet has `wheelDiameterInches` and/or a `milesPerRev`
   override, and the resulting `milesPerRev` is positive.
2. **Endpoint checks:** for each pet in pets.json, fetch
   `dataUrl?pet=<slug>`, validate JSON array shape and value ranges; unknown
   slug returns an empty array.
3. **Unit tests for `stats.js`:** dedup last-wins, date-override handling,
   distance calc, tier/threshold edge cases (including the
   `MIN_WINDOW_SAMPLES` fallback).

## Documentation

README and IMPLEMENTATION.md updated: new architecture diagram, pets.json
reference, add-a-pet runbook, revised troubleshooting (per-pet endpoint,
per-pet cache keys).

## Out of Scope (YAGNI)

- Logins/auth of any kind; per-tab sheet permissions.
- Per-pet theming/colors beyond title, name, and photo.
- Static-JSON caching via GitHub Actions (compatible future addition).
- Renaming the repo/site (URL stays `payneba.github.io/noodle-meter/`).
- Non-wheel activity types.
