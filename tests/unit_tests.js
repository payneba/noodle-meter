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
