# VPC Flow Logs

Simulates AWS VPC Flow Log records for a mix of web and API traffic patterns.

## Quick start

```bash
python generator.py -c presets/configs/vpc_flow_logs.json --template aws:cloudwatchlogs:vpcflow -n 500 -s "2025-01-01T00:00"

# One day of data
python generator.py -c presets/configs/vpc_flow_logs.json --template aws:cloudwatchlogs:vpcflow -r P1D -s "2025-01-01T00:00"

# OCSF Network Activity (security data lake / SIEM ingestion)
python generator.py -c presets/configs/vpc_flow_logs.json --template ocsf:network_activity -r P1D -s "2025-01-01T00:00"
```

## Templates

| Template | Output |
| --- | --- |
| `aws:cloudwatchlogs:vpcflow` | AWS VPC Flow Log record (`aws:cloudwatchlogs:vpcflow` sourcetype) |
| `ocsf:network_activity` | [OCSF](https://schema.ocsf.io/) 1.4.0 Network Activity (`class_uid` 4001) JSON — one event per flow record, for security data lake / SIEM ingestion |

The `ocsf:network_activity` template treats each flow record as an OCSF `activity_id: 6` ("Traffic") report, since a VPC flow record already aggregates a connection's packets/bytes over an interval rather than representing a single open/close event — this mirrors AWS's own OCSF mapping guidance for VPC Flow Logs. `direction_id`/`boundary_id` are derived from whether `srcaddr`/`dstaddr` fall in the `10.0.0.0/16` internal range (external source → Inbound/External, both internal → Lateral/Internal); `status_id` follows `ACCEPT`/`REJECT`. Verified against the real OCSF 1.4.0 `network_activity` JSON Schema across 198K generated records (0 violations).

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

## State machine

Each worker represents one network flow. The Actor captures connection attributes and a start timestamp, waits for the flow duration, then emits a single completed flow record.

```mermaid
flowchart LR
    A(["<b>connection_start</b><br/>event:start:timer"]) --> B["<b>setup_flow</b><br/>activity"]
    B --> C[/"<b>pause_flow_duration</b><br/>event:intermediate:timer"/]
    C --> D["<b>emit_flow_record</b><br/>activity"]
    D --> E(["<b>connection_end</b><br/>event:end"])
```

## Volume

The `-w` ceiling at the preset's default interarrival interval is ~66. Setting `-w` above this has no effect — the worker pool is never fully used. To model heavier network traffic, lower the interarrival interval instead (via `-i`, or by editing the config's `event:start:timer` directly).

Halving the interval (2x arrival rate) raises the ceiling to ~132; doubling it (0.5x arrival rate) lowers it to ~33. The ceiling scales linearly with arrival rate.

The table below shows how output scales with `-w` at each interval (`--seed 42`, no schedule, PT6H simulated window). To regenerate: `python tools/bench_config.py -c presets/configs/vpc_flow_logs.json --clock-field start --compare-start-interval`.

| `-w` | Rows — 1/2x interval | Rows — default | Rows — 2x interval |
| ---: | ---: | ---: | ---: |
| 1 | 6,115 | 6,116 | 6,140 |
| 2 | 11,749 | 11,771 | 11,397 |
| 3 | 17,196 | 17,362 | 16,878 |
| 6 | 34,522 | 33,806 | 33,800 |
| 12 | 68,828 | 67,583 | 64,278 |
| 22 | 126,496 | 122,248 | 97,322 |
| 41 | 231,698 | 192,555 | 99,766 |
| 76 | 386,451 | 198,392 | 99,766 |
| 142 | 400,625 | 198,392 | 99,766 |
| 264 | 400,625 | 198,392 | 99,766 |

```mermaid
xychart-beta
    title "vpc_flow_logs — rows vs -w by interarrival interval (PT6H, seed=42)"
    x-axis [1, 2, 3, 6, 12, 22, 41, 76, 142, 264]
    y-axis "Rows" 0 --> 470000
    line [6115, 11749, 17196, 34522, 68828, 126496, 231698, 386451, 400625, 400625]
    line [6116, 11771, 17362, 33806, 67583, 122248, 192555, 198392, 198392, 198392]
    line [6140, 11397, 16878, 33800, 64278, 97322, 99766, 99766, 99766, 99766]
```
