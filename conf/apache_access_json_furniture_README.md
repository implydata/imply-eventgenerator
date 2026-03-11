# Apache Access JSON — Furniture Store

See the [main README](apache_access_json_README.md) for output fields, format files, state machine, and usage examples.

## Quick Start

```bash
# Raw JSON output
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/apache_access_json.txt -m 5 -n 100

# Splunk HEC format
TARGET_SOURCE="my_host/httpd/access_json.log" TARGET_INDEX="main" \
  python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/hec_apache_access_json.txt -m 5 -n 100
```

## Details

| | |
| --- | --- |
| Config file | `conf/gen/apache_access_json_furniture.json` |
| Server IPs | `10.0.2.20`–`10.0.2.24` |

### Product categories

| Category | Weight | Example products |
| --- | --- | --- |
| Living room | 35% | Sectional sofa, leather armchair, coffee table, TV stand, bookcase |
| Bedroom | 25% | Platform bed, nightstand, dresser, wardrobe, vanity desk |
| Dining room | 15% | Dining table, dining chair, sideboard, bar stool, china cabinet |
| Office | 13% | Standing desk, task chair, filing cabinet, writing desk, bookshelf |
| Outdoor | 10% | Patio dining set, lounge chair, garden bench, hammock, Adirondack chair |

### Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~1,244 seconds (~21 minutes) |
| Interarrival mean | 3.0s (exponential) |
| Base arrival rate (λ = 1 / mean) | ~0.33 visitors/sec |
| Maximum useful `-m` (L = λW) | ~415 |

`-m` directly controls peak concurrent visitors — `-m 100` means up to 100 simultaneous sessions. The ceiling (~415) is simply the maximum the config can sustain: above it, sessions complete faster than new ones arrive to fill the pool, so extra `-m` headroom goes unused. For most use cases, set `-m` to the peak visitor count you want to simulate.

For time-of-day variation, use `--schedule schedule/ecommerce.json`. See the [schedule README](../schedule/README.md) for how schedules interact with `-m` and the ceiling.
