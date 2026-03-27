# Library scenarios

The `library/` folder contains ready-to-use generator configs. Each config embeds multiple named output templates — select one with `--template`.

## Quick reference

```bash
# Apache combined log, 100 records, simulated time
python generator.py -c library/ecommerce.json --template access_combined -n 100 -s "2025-01-01T00:00"

# JSON for Splunk TA, one hour of data
python generator.py -c library/ecommerce_lighting.json --template apache:access:json -r PT1H -s "2025-01-01T00:00"

# CSV with header row
python generator.py -c library/ecommerce.json --template csv -n 1000 -s "2025-01-01T00:00"

# AWS VPC Flow Logs
python generator.py -c library/vpc_flow_logs.json --template aws:cloudwatchlogs:vpcflow -n 500 -s "2025-01-01T00:00"
```

## E-commerce configs

Three configs simulate web access logs for an e-commerce store. They share the same state machine structure and templates, but differ in traffic volume and session behaviour.

| Config | Scenario | Interarrival mean | Typical `-m` ceiling |
| --- | --- | --- | --- |
| `ecommerce.json` | Generic store | 1.0 s | ~1,800 |
| `ecommerce_lighting.json` | Lighting retailer — busier, shorter dwell times | 0.6 s | ~2,500 |
| `ecommerce_furniture.json` | Furniture retailer — quieter, longer consideration | 3.0 s | ~750 |

All three support these templates:

| Template | Output |
| --- | --- |
| `apache:access:json` | Splunk TA JSON (`KV_MODE=json`) |
| `apache:access:kv` | Splunk TA key=value pairs |
| `apache:access:combined` | NCSA combined log (Splunk `apache:access:combined` sourcetype) |
| `access_combined` | NCSA combined log (Splunk `access_combined` pre-trained sourcetype) |
| `access_combined_wcookie` | NCSA combined log with cookie field appended |
| `access_common` | NCSA common log (no referrer or user-agent) |
| `csv` | CSV with header row |

### Output fields

| Field | Description |
| --- | --- |
| `time` | Request timestamp |
| `client` | Client IP address |
| `ident` | RFC 1413 identity (always `-`) |
| `user` | Authenticated username (usually `-`) |
| `http_method` | HTTP method (`GET`, `POST`, etc.) |
| `uri_path` | Request path |
| `uri_query` | Query string (empty if none) |
| `http_version` | Protocol version (`HTTP/1.1`, `HTTP/2.0`) |
| `status` | HTTP response status code |
| `bytes_out` | Response bytes |
| `bytes_in` | Request bytes |
| `http_referrer` | Referrer URL |
| `http_user_agent` | User-Agent string |
| `http_content_type` | Content-Type of the response |
| `cookie` | Session cookie value |
| `server` | Server IP address |
| `dest_port` | Server port (80 or 443) |
| `response_time_microseconds` | Response latency in microseconds |

### State machine overview

Workers simulate a browsing session:

```
[start] → browse_products → browse_cat → [product_detail | add_to_cart | stop]
                                                    ↓               ↓
                                              view_detail       checkout → stop
                                                    ↓
                                              [add_to_cart | stop]
```

Session-level properties (IP, user-agent, cookie, server) are drawn once at entry and persist for the full session. Page dwell times are drawn from uniform distributions (seconds to minutes, depending on category and config).

## VPC flow logs

`vpc_flow_logs.json` simulates AWS VPC Flow Log records for a mix of web and API traffic patterns.

Supports one template: `aws:cloudwatchlogs:vpcflow`

### Output fields

| Field | Description |
| --- | --- |
| `version` | Flow log version (always `2`) |
| `account_id` | AWS account ID |
| `interface_id` | Elastic network interface ID |
| `srcaddr` | Source IP address |
| `dstaddr` | Destination IP address |
| `srcport` | Source port |
| `dstport` | Destination port |
| `protocol` | IP protocol number (6=TCP, 17=UDP) |
| `packets` | Packet count for the flow |
| `bytes` | Byte count for the flow |
| `start` | Flow start time (Unix epoch) |
| `end` | Flow end time (Unix epoch) |
| `action` | `ACCEPT` or `REJECT` |
| `log_status` | `OK`, `NODATA`, or `SKIPDATA` |

## Using with schedules

Combine any library config with a schedule file to add time-of-day traffic variation:

```bash
python generator.py -c library/ecommerce.json --template access_combined \
  -m 500 --schedule schedule/ecommerce.json
```

See [schedule documentation](../docs/schedule.md) for details.

## Using with targets

By default, output goes to stdout. To send to Kafka or a file, use `-t`:

```bash
python generator.py -c library/ecommerce.json --template apache:access:json \
  -t conf/tar/kafka.json
```

See [target documentation](../docs/tarspec.md) for configuration details.
