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
