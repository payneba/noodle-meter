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

    return {
        TIER_WINDOW_DAYS,
        HISTOGRAM_WINDOW_DAYS,
        MIN_WINDOW_SAMPLES,
        calculatePercentile,
        windowThresholds,
        trailingDistances,
        computeTiers,
        milesPerRev,
        normalizeRows
    };
}));
