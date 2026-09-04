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

    h.test('milesPerRev from wheel diameter', () => {
        h.assertClose(Stats.milesPerRev({ wheelDiameterInches: 9 }),
            Math.PI * 9 / 63360, 1e-12, 'diameter-derived');
    });

    h.test('milesPerRev override wins over diameter', () => {
        h.assertEqual(Stats.milesPerRev({ wheelDiameterInches: 9, milesPerRev: 0.5 }),
            0.5, 'override');
    });

    h.test('milesPerRev honors explicit zero override', () => {
        h.assertEqual(Stats.milesPerRev({ wheelDiameterInches: 9, milesPerRev: 0 }),
            0, 'explicit zero is a real override, not "unset"');
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

    h.test('normalizeRows treats date-only ISO override as a calendar date', () => {
        const out = Stats.normalizeRows(
            [{ timestamp: '2026-01-05T14:00:00Z', revs: 500, date: '2026-01-03' }], 0.001);
        h.assertEqual(out[0].date, new Date(2026, 0, 3).toLocaleDateString('en-US'),
            'no timezone shift for date-only ISO override');
    });

    h.test('normalizeRows treats Apps Script Date-cell override as a calendar date', () => {
        const out = Stats.normalizeRows(
            [{ timestamp: '2026-01-05T14:00:00Z', revs: 500, date: '2026-01-03T05:00:00.000Z' }], 0.001);
        h.assertEqual(out[0].date, new Date(2026, 0, 3).toLocaleDateString('en-US'),
            'no timezone shift for UTC-midnight-Eastern override timestamp');
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

    h.test('normalizeRows dedup ignores sheet order, uses latest timestamp (form above backfill)', () => {
        // Google Forms inserts new responses above manually pasted backfill
        // rows, so a form-submitted correction can appear earlier in the
        // sheet than the stale backfill row it's correcting.
        const out = Stats.normalizeRows([
            { timestamp: '2026-06-01T14:00:00Z', revs: 999, date: '2026-01-15' },
            { timestamp: '2026-01-15T14:00:00Z', revs: 100, date: '' }
        ], 0.001);
        h.assertEqual(out.length, 1, 'deduped to one entry for 1/15/2026');
        h.assertEqual(out[0].revs, 999, 'later-timestamped correction wins despite appearing first in sheet order');
    });

    h.test('normalizeRows same-day resubmit ordering is timestamp-based, not array-order-based', () => {
        const out = Stats.normalizeRows([
            { timestamp: '2026-01-05T16:00:00Z', revs: 200, date: '' },
            { timestamp: '2026-01-05T14:00:00Z', revs: 100, date: '' }
        ], 0.001);
        h.assertEqual(out.length, 1, 'deduped');
        h.assertEqual(out[0].revs, 200, 'later timestamp wins even though it is first in the array');
    });
}

module.exports = { run };
