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
