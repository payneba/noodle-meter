// Schema tests: pets.json is well-formed and internally consistent.
const fs = require('fs');
const path = require('path');
const Stats = require('../stats.js');

async function run(h) {
    console.log('\nSchema tests (pets.json)');

    let config;
    h.test('pets.json parses', () => {
        config = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'pets.json'), 'utf8'));
    });
    if (!config) return;

    h.test('dataUrl is an https URL', () => {
        h.assertTrue(typeof config.dataUrl === 'string' &&
            config.dataUrl.startsWith('https://'), `bad dataUrl: ${config.dataUrl}`);
    });

    h.test('pets is a non-empty array', () => {
        h.assertTrue(Array.isArray(config.pets) && config.pets.length > 0, 'pets array');
    });

    h.test('slugs are well-formed and unique', () => {
        const slugs = config.pets.map(p => p.slug);
        slugs.forEach(s => h.assertTrue(/^[a-z0-9_-]+$/.test(s), `bad slug: ${s}`));
        h.assertEqual(new Set(slugs).size, slugs.length, 'unique slugs');
    });

    config.pets.forEach(pet => {
        h.test(`pet '${pet.slug}' has name, title, formUrl`, () => {
            h.assertTrue(typeof pet.name === 'string' && pet.name.length > 0, 'name');
            h.assertTrue(typeof pet.title === 'string' && pet.title.length > 0, 'title');
            h.assertTrue(typeof pet.formUrl === 'string' &&
                pet.formUrl.startsWith('https://'), 'formUrl');
        });
        h.test(`pet '${pet.slug}' image file exists`, () => {
            h.assertTrue(fs.existsSync(path.join(__dirname, '..', pet.image)),
                `missing ${pet.image}`);
        });
        h.test(`pet '${pet.slug}' has a positive milesPerRev`, () => {
            const perRev = Stats.milesPerRev(pet);
            h.assertTrue(isFinite(perRev) && perRev > 0, `milesPerRev = ${perRev}`);
        });
    });
}

module.exports = { run };
