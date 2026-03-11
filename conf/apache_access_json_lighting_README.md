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
| Natural steady-state concurrency (L = λW) | ~1,365 |

`-m` sets peak concurrent workers. For realistic temporal variation (busier on weekday afternoons, quiet overnight), use `--schedule schedule/ecommerce.json`. Setting `-m` at or above the natural L (~1,365) means the schedule drives active worker count freely. At lower `-m` values the cap still bites at peak, but the schedule will reduce active workers to a fraction of `-m` at off-peak times, preserving temporal variation.
