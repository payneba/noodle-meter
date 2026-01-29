// Simple test runner for Noodle Meter
// Run with: node tests.js

const https = require('https');

const DATA_URL = 'https://script.google.com/macros/s/AKfycbxoKRMGYPQAxMCUerc8ZO2MPxJl_aeTZRwIzMYej86asddpN4IzkjgOggQMnLtKUCIzuQ/exec';

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

function fetch(url) {
    return new Promise((resolve, reject) => {
        const makeRequest = (url) => {
            https.get(url, (res) => {
                // Handle redirects
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

async function runTests() {
    console.log('Running Noodle Meter Tests\n');

    // Test 1: Apps Script endpoint responds
    let responseData;
    try {
        const response = await fetch(DATA_URL);
        test('Apps Script endpoint responds with 200', () => {
            assertEqual(response.status, 200, 'Status code');
        });
        responseData = response.data;
    } catch (error) {
        test('Apps Script endpoint responds with 200', () => {
            throw error;
        });
    }

    // Test 2: Response is valid JSON
    let jsonData;
    test('Response is valid JSON', () => {
        jsonData = JSON.parse(responseData);
        assertTrue(true, 'JSON parsed successfully');
    });

    // Test 3: Response is an array
    test('Response is an array', () => {
        assertTrue(Array.isArray(jsonData), 'Response should be an array');
    });

    // Test 4: Array has data
    test('Response contains data', () => {
        assertTrue(jsonData.length > 0, 'Array should not be empty');
    });

    // Test 5: Data has expected fields
    test('Data has expected fields (date, revs, distance)', () => {
        const first = jsonData[0];
        assertTrue('date' in first, 'Missing date field');
        assertTrue('revs' in first, 'Missing revs field');
        assertTrue('distance' in first, 'Missing distance field');
    });

    // Test 6: Distance values are reasonable
    test('Distance values are reasonable (0-50 miles)', () => {
        jsonData.forEach((row, i) => {
            const dist = Number(row.distance);
            assertTrue(dist >= 0 && dist <= 50, `Row ${i}: distance ${dist} out of range`);
        });
    });

    // Test 7: Revs are positive integers
    test('Revolution counts are positive', () => {
        jsonData.forEach((row, i) => {
            const revs = Number(row.revs);
            assertTrue(revs >= 0, `Row ${i}: revs ${revs} should be positive`);
        });
    });

    // Summary
    console.log(`\n${passed} passed, ${failed} failed`);
    process.exit(failed > 0 ? 1 : 0);
}

runTests();
