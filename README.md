# Noodle Meter

A web app to track how many miles Noodle the hamster runs each night.

## About

Running data is captured using a [Niteangel Hamster Wheel Pedometer](https://www.niteangelpet.com/search?q=pedometer) which counts wheel revolutions. The daily totals are logged in a Google Sheet and displayed here with fun visual effects based on performance.

## Live Site

https://payneba.github.io/noodle-meter/

## Implementation

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details, external dependencies, and deployment instructions.

## Analysis

Noodle's nightly mileage has been falling since January — but she isn't slowing down.
She runs from lights-out to sunrise, and that window shrinks by ~2 hours between
January and the summer solstice, which accounts for ~85% of the decline.

See [analysis/README.md](analysis/README.md) for the full write-up, and
`analysis/photoperiod_model.py` to re-derive it from live data. This is also why the
app grades each night against the trailing 30 days rather than against all-time
percentiles.
