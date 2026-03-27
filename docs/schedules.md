# Schedules

A schedule modulates the number of active workers over time, producing realistic variation in data volume — busier during peak hours, quieter overnight and at weekends.

## Usage

```bash
python generator.py -c conf/gen/apache_access_json_lighting.json -m 500 --schedule schedule/ecommerce.json
```

Without `--schedule`, the generator runs at full capacity (`-m` workers) at all times.

## How it works

The schedule defines a multiplier between 0 and 1 for any point in time. The generator applies this to `-m` to compute the effective worker cap:

```
effective workers = -m × schedule_multiplier
```

At peak (multiplier = 1.0), the full `-m` is in effect. At off-peak (e.g. multiplier = 0.2), only 20% of `-m` workers are active. This means **`-m` sets the peak; the schedule shapes everything below it**.

## The ceiling

Every config has a natural concurrency ceiling determined by its state machine and interarrival time (documented in each config's README). If `-m` exceeds this ceiling, the schedule pattern will not appear cleanly at peak — the generator hits the ceiling before it reaches `-m`, producing a plateau rather than a smooth curve. Set `-m` at or below the ceiling for the schedule to drive the full shape of the data.

## Available schedules

### `full.json`

```json
{"type": "constant", "value": 1.0}
```

Flat multiplier of 1.0 at all times — equivalent to running without `--schedule`. Useful as an explicit default or when you want the schedule infrastructure in place without any variation.

### `ecommerce.json`

A realistic e-commerce traffic pattern: weekday afternoons are busiest, evenings taper off, nights and early mornings are quiet. Weekends have lighter, later-shifting peaks.

| Day | Peak UTC hour(s) | Peak weight |
| --- | --- | --- |
| Monday | 14:00 | 0.72 |
| Tuesday | 12:00 | 1.00 (overall peak) |
| Friday | 11:00 | 0.89 |
| Saturday | 14:00 | 0.56 |
| Sunday | 13:00 | 0.44 |

Days not listed (Wednesday, Thursday) fall back to a flat baseline. All weights are normalised so the highest value across the week is 1.0.

## Writing your own schedule

A schedule file is a JSON object with a `type` field.

**Constant** — always the same multiplier:

```json
{"type": "constant", "value": 0.5}
```

**GMM temporal** — Gaussian mixture model varying by day of week and time of day:

```json
{
  "type": "gmm_temporal",
  "days": {
    "1": [
      {"utc_hour": 9,  "sigma": 2.0, "weight": 0.8},
      {"utc_hour": 17, "sigma": 1.5, "weight": 0.6}
    ],
    "6": [
      {"utc_hour": 12, "sigma": 3.0, "weight": 0.4}
    ]
  }
}
```

- `days` keys are ISO weekday numbers: `1` = Monday … `7` = Sunday
- Days not listed in `days` produce a multiplier of 0 (no active workers)
- Each entry is a Gaussian component: `utc_hour` is the centre, `sigma` is the width in hours, `weight` is the peak multiplier for that component
- Multiple components in the same day are summed, then clamped to [0, 1]
- Weights should be normalised so the maximum across the whole week is 1.0 — otherwise `-m` will never be fully utilised even at peak
