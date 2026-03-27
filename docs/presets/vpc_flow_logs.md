# VPC Flow Logs

Simulates AWS VPC Flow Log records for a mix of web and API traffic patterns.

Supports one template: `aws:cloudwatchlogs:vpcflow`

## Quick start

```bash
python generator.py -c presets/configs/vpc_flow_logs.json --template aws:cloudwatchlogs:vpcflow -n 500 -s "2025-01-01T00:00"

# One day of data
python generator.py -c presets/configs/vpc_flow_logs.json --template aws:cloudwatchlogs:vpcflow -r P1D -s "2025-01-01T00:00"
```

## Output fields

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

## Concurrency (`-m`)

| Little's Law component | Value |
| --- | --- |
| Average session duration (W) | ~13 seconds |
| Interarrival mean | 0.5 s |
| Base arrival rate (λ = 1/mean) | ~2.0 connections/sec |
| Maximum useful `-m` (L = λW) | ~25 |

Setting `-m` above ~25 has no effect — connections are short-lived and complete faster than new ones arrive.
