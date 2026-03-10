# Apache Access JSON Log Generator

> **Deprecation notice:** `conf/gen/apache_access_json.json` has been renamed to `conf/gen/apache_access_json_lighting.json`. The original file will be removed in a future release. Please update your scripts and pipelines to use the new name.

## Overview

These configurations generate realistic Apache access log records in the Splunk [`apache:access:json`](https://docs.splunk.com/Documentation/AddOns/released/ApacheWebServer/Configure) format. Each variant simulates user sessions on an e-commerce website with typical browsing behavior including product discovery, category browsing, cart management, and checkout, along with a small proportion of malicious traffic from automated attack tools.

The interarrival rate uses a [`gmm_temporal`](../docs/distributions.md#gmm_temporal) distribution to model realistic daily traffic patterns — higher rates during business hours, lower overnight, with distinct profiles for Monday, Tuesday–Thursday, Friday, and weekends. Use a higher `-m` value (e.g., `-m 50`) for the full effect — low concurrency caps the number of active visitors, compressing the volume differences between peak and off-peak periods.

The field names and structure are derived from an analysis of the [Splunk Add-on for Apache Web Server](https://docs.splunk.com/Documentation/AddOns/released/ApacheWebServer/Sourcetypes) (`Splunk_TA_apache`). The TA's `props.conf` and `transforms.conf` for the `apache:access:json` sourcetype expect specific raw field names (e.g., `client`, `server`, `bytes_in`, `uri_path`, `response_time_microseconds`) and apply EVAL expressions and field aliases to map them to the Splunk CIM. The event generator uses these raw field names so that the TA works correctly without modification — field renaming and CIM mapping should be left to the TA, not done at the source.

## Variants

All variants follow the same state machine structure, output fields, and format files — only the product catalog, URIs, and server IPs differ.

| Variant | Config file | Docs |
| --- | --- | --- |
| Lighting store | `conf/gen/apache_access_json_lighting.json` | [README](apache_access_json_lighting_README.md) |
| Furniture store | `conf/gen/apache_access_json_furniture.json` | [README](apache_access_json_furniture_README.md) |

## Output fields

| Field | Description | Example |
| --- | --- | --- |
| `time` | Request timestamp (epoch seconds) | `1770979284` |
| `server` | Server IP address | `10.0.1.15` |
| `ident` | Identity (always `-`) | `-` |
| `user` | Authenticated username | `natalie38` |
| `http_method` | HTTP method | `GET`, `POST` |
| `uri_path` | Requested URL path | `/categories/indoor-lighting/aurora-chandelier` |
| `uri_query` | Query string | ``, `?user=admin'--` |
| `http_content_type` | Request Content-Type header | `-`, `application/x-www-form-urlencoded` |
| `status` | HTTP response status code | `200`, `404`, `403` |
| `bytes_out` | Response size in bytes | `4521` |
| `bytes_in` | Request size in bytes | `230` |
| `http_referrer` | Referring URL | `https://www.google.com/` |
| `client` | Client IP address | `63.211.68.115` |
| `http_user_agent` | Client user agent string | `Mozilla/5.0 ...` |
| `dest_port` | Server destination port | `443`, `80`, `8080` |
| `response_time_microseconds` | Server response time in microseconds | `25971` |
| `cookie` | Cookie header (always `-`) | `-` |

## Format files

| File | Description |
| --- | --- |
| `conf/form/apache_access_json.txt` | Raw `apache:access:json` events, one JSON object per line |
| `conf/form/hec_apache_access_json.txt` | Splunk / Lumi HEC envelope with the event nested inside |

### HEC format details

The HEC format wraps each event in a [Splunk HEC envelope](https://docs.splunk.com/Documentation/SplunkCloud/latest/Data/FormateventsforHTTPEventCollector) with the following metadata:

| Field | Value |
| --- | --- |
| `source` | `%TARGET_SOURCE%` (set via environment variable) |
| `sourcetype` | `apache:access:json` |
| `index` | `%TARGET_INDEX%` (set via environment variable) |
| `host` | Server IP from generated data |
| `time` | Epoch seconds (unquoted number) |

Set the environment variables when running the generator:

```bash
TARGET_SOURCE="my_host/httpd/access_json.log" TARGET_INDEX="main" \
  python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/hec_apache_access_json.txt -m 10 -n 1000
```

## State machine

Each worker simulates a user session through the following flow:

```text
initial → browse_products → browse category → add_to_cart → checkout → thank_you
              ↑                    |                            |
              └────────────────────┘                       try_again
                                                         (400 status)

initial → hacker (0.1% of sessions)
           ↻ rapid requests to admin/sensitive paths
```

**Normal traffic (99.9%)**: Users arrive, browse product categories, optionally add items to cart and check out. Category browsing uses exponential distribution to create realistic product popularity curves.

**Malicious traffic (0.1%)**: Automated scans that rapidly probe admin paths, config files, and common vulnerabilities, generating `403`, `404`, and `500` status codes. Attack payloads appear in `uri_query` (e.g., SQL injection, debug parameters).

## Usage examples

The examples below use the lighting variant; substitute the config file path for other variants.

Generate a full day of data starting from yesterday at midnight:

```bash
python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/apache_access_json.txt -s 2025-01-15T00:00:00 -r PT24H -m 10
```

Use a bash script to automatically generate yesterday's data:

```bash
#!/bin/bash
# Generate a full day of apache:access:json data for yesterday

YESTERDAY=$(date -u -v-1d +"%Y-%m-%dT00:00:00")  # macOS
# YESTERDAY=$(date -u -d "yesterday" +"%Y-%m-%dT00:00:00")  # Linux

python generator.py \
  -c conf/gen/apache_access_json_lighting.json \
  -f conf/form/apache_access_json.txt \
  -s "$YESTERDAY" \
  -r PT24H \
  -m 10 \
 ```

Generate 10 records as raw JSON:

```bash
python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/apache_access_json.txt -m 1 -n 10
```

Generate in Splunk HEC format for ingestion into Splunk or Lumi:

```bash
TARGET_SOURCE="my_host/httpd/access_json.log" TARGET_INDEX="main" \
  python generator.py -c conf/gen/apache_access_json_lighting.json -f conf/form/hec_apache_access_json.txt -m 10 -n 1000
```

Generate deterministic data (same seed = same output):

```bash
python generator.py \
  -c conf/gen/apache_access_json_lighting.json \
  -f conf/form/apache_access_json.txt \
  -s "2026-02-12T00:00:00" \
  -r P1D \
  --seed 42
```

Generate without a format file (default JSON with ISO timestamps):

```bash
python generator.py -c conf/gen/apache_access_json_lighting.json -m 1 -n 10
```

## Use cases

- **Splunk / Lumi ingestion testing**: HEC-compliant events with correct `apache:access:json` sourcetype
- **Web analytics testing**: Realistic clickstream data with browsing funnels and conversion paths
- **Security monitoring**: Detect attack patterns mixed in with legitimate traffic, with injection payloads in `uri_query`
- **Log pipeline testing**: Test ingestion with structured JSON Apache logs
- **E-commerce analytics**: Funnel analysis, category popularity, cart abandonment rates
