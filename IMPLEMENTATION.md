# Noodle Meter - Implementation Details

## Overview

A simple web app to track daily running distances for Noodle the hamster. Displays distance data with visual effects based on performance tiers.

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Google Sheet   │ ──── │ Google Apps      │ ──── │  GitHub Pages   │
│  (data entry)   │      │ Script (API)     │      │  (web app)      │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

## External Dependencies

### 1. Google Sheet

- **URL**: https://docs.google.com/spreadsheets/d/1AkG8AGDzFvb4OnOU2qTY3FrM3lkKCM0WOeHSLyX_tNE
- **Purpose**: Primary data store for daily hamster running stats
- **Columns**:
  - `Date Checked` - Date in M/d/yyyy format
  - `Revs` - Wheel revolution count (integer)
  - `Distance (mi)` - Calculated distance in miles (decimal)
- **Access**: Sheet must be shared as "Anyone with the link can view"

### 2. Google Apps Script

- **Purpose**: Serves sheet data as JSON with CORS headers (bypasses browser restrictions)
- **Deployment URL**: https://script.google.com/macros/s/AKfycbxoKRMGYPQAxMCUerc8ZO2MPxJl_aeTZRwIzMYej86asddpN4IzkjgOggQMnLtKUCIzuQ/exec
- **Bound to**: The Google Sheet above

#### Apps Script Code

To recreate, go to the Google Sheet → Extensions → Apps Script, and add:

```javascript
function doGet() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = sheet.getDataRange().getValues();

  // Skip header row, convert to objects
  var result = [];
  for (var i = 1; i < data.length; i++) {
    result.push({
      date: data[i][0],
      revs: data[i][1],
      distance: data[i][2]
    });
  }

  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}
```

#### Deployment Settings

- Deploy → New deployment → Web app
- Execute as: **Me**
- Who has access: **Anyone**

After deploying, copy the web app URL to `index.html` (the `DATA_URL` constant).

### 3. GitHub Pages

- **Repository**: https://github.com/payneba/noodle-meter
- **Pages URL**: https://payneba.github.io/noodle-meter/
- **Branch**: `main`
- **Settings**: Settings → Pages → Deploy from branch → main / root

## Local Files

| File | Purpose |
|------|---------|
| `index.html` | Complete web app (HTML, CSS, JS in single file) |
| `noodle_cropped.jpg` | Hamster photo displayed at top of page |
| `tests.js` | Node.js tests for validating data endpoint |
| `.github/workflows/test.yml` | GitHub Actions workflow to run tests on push |

## Features

### Visual Tiers (based on percentiles)

| Tier | Condition | Color | Effects |
|------|-----------|-------|---------|
| Low | Below 25th percentile | Blue | Smaller text |
| Medium | 25th-75th percentile | Green | Normal text |
| High | Above 75th percentile | Orange | Larger text, glow |
| Record | Highest ever | Red | Largest text, pulse animation, confetti |

### Caching

- Uses `localStorage` to cache data
- Cache is valid only if:
  - Cached today
  - Contains today's data
- If today's data not in sheet yet, cache is skipped (ensures fresh fetch)

## Testing

Run tests locally (requires Node.js):

```bash
node tests.js
```

Tests validate:
- Apps Script endpoint responds
- Response is valid JSON array
- Data has expected fields (date, revs, distance)
- Values are in reasonable ranges

## Troubleshooting

### "Could not load data" error

1. Check Apps Script deployment is set to "Anyone" access
2. Verify the deployment URL in `index.html` matches current deployment
3. Check browser console for specific error messages

### Data not updating

1. Clear localStorage: Open browser console → `localStorage.clear()`
2. Verify new data exists in Google Sheet
3. Check that date format in sheet matches expected M/d/yyyy format

### Apps Script changes not reflected

After editing Apps Script code, you must create a **new deployment**:
1. Deploy → New deployment (not "Manage deployments")
2. Update the URL in `index.html`
3. Commit and push changes

## Future Improvements

- [ ] GitHub Actions to cache data as static JSON (faster first load)
- [ ] Historical charts/graphs
- [ ] Weekly/monthly summaries
