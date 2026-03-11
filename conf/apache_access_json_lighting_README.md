# Apache Access JSON — Lighting Store

See the [main README](apache_access_json_README.md) for output fields, format files, state machine, and usage examples.

## Quick Start

```bash
# Raw JSON output
python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/apache_access_json.txt -m 5 -n 100

# Splunk HEC format
TARGET_SOURCE="my_host/httpd/access_json.log" TARGET_INDEX="main" \
  python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/hec_apache_access_json.txt -m 5 -n 100
```

## Details

| | |
| --- | --- |
| Config file | `conf/gen/apache_access_json_lighting.json` |
| Server IPs | `10.0.1.15`–`10.0.1.19` |

### Product categories

| Category | Weight | Example products |
| --- | --- | --- |
| Indoor | 40% | Aurora chandelier, nebula table lamp, stellar floor lamp, eclipse wall sconce |
| Outdoor | 20% | Solar path light, moonlit garden lamp, starlight wall lantern |
| Smart | 15% | Voice-controlled bulb, color-changing bulb, wifi LED strip |
| LED | 15% | Ultra bright LED bulb, eco-friendly LED panel, LED desk lamp |
| Vintage | 8% | Retro chandelier, antique wall lamp, industrial pendant light |

### Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~819 seconds (~14 minutes) |
| Interarrival mean | 0.6s (exponential) |
| Base arrival rate (λ = 1 / mean) | ~1.67 visitors/sec |
| Maximum useful `-m` (L = λW) | ~1,365 |

`-m` directly controls peak concurrent visitors — `-m 200` means up to 200 simultaneous sessions. The ceiling (~1,365) is simply the maximum the config can sustain: above it, sessions complete faster than new ones arrive to fill the pool, so extra `-m` headroom goes unused. For most use cases, set `-m` to the peak visitor count you want to simulate.

For time-of-day variation, use `--schedule conf/schedule/ecommerce.json`. See the [schedule documentation](../docs/schedule.md) for how schedules interact with `-m` and the ceiling.
