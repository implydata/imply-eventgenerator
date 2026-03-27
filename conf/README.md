# conf/ — Deprecated

> **Deprecated:** This folder and all configs within it are deprecated and will be removed in a future release.
> Use [`presets/`](../presets/README.md) instead.

## Configs

| Config | Status | Replacement |
| --- | --- | --- |
| `conf/gen/apache_access_combined.json` | Deprecated | [`presets/configs/ecommerce.json`](../docs/presets/ecommerce.md) |
| `conf/gen/apache_access_json.json` | Deprecated | [`presets/configs/ecommerce.json`](../docs/presets/ecommerce.md) |
| `conf/gen/apache_access_json_lighting.json` | Deprecated | [`presets/configs/ecommerce_lighting.json`](../docs/presets/ecommerce_lighting.md) |
| `conf/gen/apache_access_json_furniture.json` | Deprecated | [`presets/configs/ecommerce_furniture.json`](../docs/presets/ecommerce_furniture.md) |
| `conf/gen/vpc_flow_logs.json` | Deprecated | [`presets/configs/vpc_flow_logs.json`](../docs/presets/vpc_flow_logs.md) |
| [`conf/gen/clickstream.json`](../docs/conf/clickstream.md) | Deprecated — no replacement | — |
| [`conf/gen/social_posts.json`](../docs/conf/social_posts.md) | Deprecated — no replacement | — |

## Format files

All format files are deprecated. Use `--template` with a `presets/configs/` config instead. See [docs/templates.md](../docs/templates.md).

| File | Description | Replacement |
| --- | --- | --- |
| `conf/form/apache_access_json.txt` | `apache:access:json` one JSON object per line | `--template apache:access:json` |
| `conf/form/csv_apache_access_json.txt` | CSV with header row | `--template csv` |
| `conf/form/hec_apache_access_json.txt` | Splunk HEC envelope | No direct replacement |
| `conf/form/hec_apache_access_combined.txt` | Splunk HEC envelope (combined) | No direct replacement |
| `conf/form/tsv_apache_access_combined.txt` | TSV combined log | No direct replacement |
| `conf/form/clickstream_tsv.txt` | Clickstream TSV | No direct replacement |
| `conf/form/vpc_flow_logs.txt` | VPC flow log format | `--template aws:cloudwatchlogs:vpcflow` |

## Schedules

Schedules have moved to [`presets/schedules/`](../presets/README.md).

| File | Replacement |
| --- | --- |
| `conf/schedule/ecommerce.json` | [`presets/schedules/ecommerce.json`](../presets/schedules/ecommerce.json) |
| `conf/schedule/full.json` | [`presets/schedules/full.json`](../presets/schedules/full.json) |
