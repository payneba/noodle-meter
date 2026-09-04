# Noodle Meter

A web app to track how many miles a hamster runs each night. Started as
Noodle's tracker; now supports multiple pets/wheels.

## About

Each pet's running data is captured using a [Niteangel Hamster Wheel Pedometer](https://www.niteangelpet.com/search?q=pedometer) which counts wheel revolutions. Owners read the pedometer each morning and submit the count through that pet's Google Form. Submissions land in a shared spreadsheet (one tab per pet) and are displayed here — at `?pet=<slug>` — with fun visual effects based on performance.

## Live Site

https://payneba.github.io/noodle-meter/ (add `?pet=<slug>` for a specific pet; defaults to the last one you viewed, or the first configured pet)

## Implementation

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for technical details, external dependencies, deployment instructions, and the runbook for adding a new pet.

## Analysis

Noodle's nightly mileage has been falling since January — mostly, but not entirely,
because of daylight. She runs from lights-out to sunrise, and that window shrinks by
~2 hours between January and the summer solstice. With data through early September,
that shrinking dark window accounts for roughly 86% of the decline — but the leftover
trend is now small and statistically significant: about −30 revs/day on top of the
photoperiod effect. Most of the "slowdown" is the season; there's now evidence of a
modest genuine slowdown underneath it too.

See [analysis/README.md](analysis/README.md) for the full write-up (Noodle-specific;
it predates multi-pet support), and `analysis/photoperiod_model.py` to re-derive it
from live data. This is also why the app grades each night against the trailing 30
days rather than against all-time percentiles.
