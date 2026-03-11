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

The realistic maximum for `-m` (concurrent workers) for this configuration is **2,500**.

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~819 seconds (~14 minutes) |
| Interarrival mean | 0.6s |
| Base arrival rate (λ = 1 / mean) | ~1.67 visitors/sec |
| Peak GMM multiplier | 1.8× (Tuesday midday) |
| Peak arrival rate (λ × multiplier) | ~3.0 visitors/sec |
| Peak steady-state concurrency (L = λW) | ~2,460 |
