# Apache Access Combined Log Generator

## Quick Start

```bash
# JSON output
python generator.py -c conf/gen/apache_access_combined.json -m 5 -n 100 
# TSV output
python generator.py -c conf/gen/apache_access_combined.json -f conf/form/tsv_apache_access_combined.txt -m 5 -n 100 ```

## Overview

This configuration generates realistic [Apache access combined log](https://httpd.apache.org/docs/2.4/logs.html) records that simulate user sessions on a lighting e-commerce website. The generator models typical browsing behavior including product discovery, category browsing, cart management, and checkout, along with a small proportion of malicious traffic from automated attack tools.

## Output fields

| Field | Description | Example |
| --- | --- | --- |
| `time` | Request timestamp | `23/Sep/2023:14:30:00 +0000` |
| `host` | Server IP address | `10.0.1.15` |
| `ident` | Identity (always `-`) | `-` |
| `authuser` | Authenticated username | `natalie38` |
| `request_method` | HTTP method | `GET`, `POST` |
| `request_url` | Requested URL path | `/categories/indoor-lighting/aurora-chandelier` |
| `request_protocol` | HTTP protocol version | `HTTP/1.1`, `HTTP/2` |
| `status` | HTTP response status code | `200`, `404`, `403` |
| `bytes` | Response size in bytes | `4521` |
| `referrer_url` | Referring URL | `https://www.google.com/` |
| `clientip` | Client IP address | `63.211.68.115` |
| `useragent` | Client user agent string | `Mozilla/5.0 ...` |

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

**Normal traffic (99.9%)**: Users arrive, browse product categories (indoor, outdoor, smart, LED, vintage lighting), optionally add items to cart and check out. Category browsing uses exponential distribution to create realistic product popularity curves.

**Malicious traffic (0.1%)**: Automated scans that rapidly probe admin paths, config files, and common vulnerabilities, generating `403`, `404`, and `500` status codes.

## Usage examples

Generate 10 records as JSON:

```bash
python generator.py -c conf/gen/apache_access_combined.json -m 1 -n 10 ```

Generate in Apache combined log format:

```bash
python generator.py -c conf/gen/apache_access_combined.json -f conf/form/tsv_apache_access_combined.txt -m 10 -n 1000 ```

Generate in Splunk HEC format:

```bash
python generator.py -c conf/gen/apache_access_combined.json -f conf/form/hec_apache_access_combined.txt -m 10 -n 1000 ```

## Use cases

- **Web analytics testing**: Realistic clickstream data with browsing funnels and conversion paths
- **Security monitoring**: Detect attack patterns mixed in with legitimate traffic
- **Log pipeline testing**: Test ingestion with standard Apache combined log format
- **E-commerce analytics**: Funnel analysis, category popularity, cart abandonment rates
