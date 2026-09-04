// Test runner for Noodle Meter. Run with: node tests.js
const harness = require('./tests/harness');

(async () => {
    console.log('Running Noodle Meter Tests');
    await require('./tests/unit_tests').run(harness);
    await require('./tests/endpoint_tests').run(harness);
    harness.summary();
})();
