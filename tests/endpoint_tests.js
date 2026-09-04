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
