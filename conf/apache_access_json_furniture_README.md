# Apache Access JSON Log Generator (Furniture Store)

## Quick Start

```bash
# JSON output (raw apache:access:json events)
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/apache_access_json.txt -m 5 -n 100
```

```bash
# Splunk HEC format
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/hec_apache_access_json.txt -m 5 -n 100
```

## Overview

This configuration generates realistic Apache access log records in the Splunk [`apache:access:json`](https://docs.splunk.com/Documentation/AddOns/released/ApacheWebServer/Configure) format. It simulates user sessions on a **furniture e-commerce website** with typical browsing behavior including product discovery, category browsing, cart management, and checkout, along with a small proportion of malicious traffic from automated attack tools.

This is a thematic variant of the [lighting store](apache_access_json_README.md) configuration — same state machine structure and output format, different product catalog.

The interarrival rate uses a [`gmm_temporal`](../docs/distributions.md#gmm_temporal) distribution to model realistic daily traffic patterns — higher rates during business hours, lower overnight, with distinct profiles for Monday, Tuesday–Thursday, Friday, and weekends. Use a higher `-m` value (e.g., `-m 50`) for the full effect — low concurrency caps the number of active visitors, compressing the volume differences between peak and off-peak periods.

## Output fields

| Field | Description | Example |
| --- | --- | --- |
| `time` | Request timestamp (epoch seconds) | `1770979284` |
| `server` | Server IP address | `10.0.2.20` |
| `ident` | Identity (always `-`) | `-` |
| `user` | Authenticated username | `marcus_reed` |
| `http_method` | HTTP method | `GET`, `POST` |
| `uri_path` | Requested URL path | `/categories/living-room/hampton-sectional-sofa` |
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

This configuration uses the same format templates as the lighting store variant:

| File | Description |
| --- | --- |
| `conf/form/apache_access_json.txt` | Raw `apache:access:json` events, one JSON object per line |
| `conf/form/hec_apache_access_json.txt` | Splunk / Lumi HEC envelope with the event nested inside |

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

**Normal traffic (99.9%)**: Users arrive, browse product categories (living room, bedroom, dining room, office, outdoor furniture), optionally add items to cart and check out. Category browsing uses exponential distribution to create realistic product popularity curves.

**Product categories:**

| Category | Example products |
| --- | --- |
| Living room (35%) | Sectional sofa, leather armchair, coffee table, TV stand, bookcase |
| Bedroom (25%) | Platform bed, nightstand, dresser, wardrobe, vanity desk |
| Dining room (15%) | Dining table, dining chair, sideboard, bar stool, china cabinet |
| Office (13%) | Standing desk, task chair, filing cabinet, writing desk, bookshelf |
| Outdoor (10%) | Patio dining set, lounge chair, garden bench, hammock, Adirondack chair |

**Malicious traffic (0.1%)**: Automated scans that rapidly probe admin paths, config files, and common vulnerabilities, generating `403`, `404`, and `500` status codes. Attack payloads appear in `uri_query` (e.g., SQL injection, debug parameters).

## Usage examples

Generate a full day of data starting from yesterday at midnight:

```bash
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/apache_access_json.txt -s 2025-01-15T00:00:00 -r PT24H -m 10
```

Generate 10 records as raw JSON:

```bash
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/apache_access_json.txt -m 1 -n 10
```

Generate in Splunk HEC format for ingestion into Splunk or Lumi:

```bash
python generator.py -c conf/gen/apache_access_json_furniture.json -f conf/form/hec_apache_access_json.txt -m 10 -n 1000
```

Generate deterministic data (same seed = same output):

```bash
python generator.py \
  -c conf/gen/apache_access_json_furniture.json \
  -f conf/form/apache_access_json.txt \
  -s "2026-02-12T00:00:00" \
  -r P1D \
  --seed 42
```
