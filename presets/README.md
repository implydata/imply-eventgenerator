# Presets

Ready-to-use generator configs and schedules. Each config embeds named output templates — select one with `--template`.

## Configs

| Config | Scenario | `-m` ceiling |
| --- | --- | --- |
| [`ecommerce.json`](../docs/presets/ecommerce.md) | Generic e-commerce store | ~1,800 |
| [`ecommerce_lighting.json`](../docs/presets/ecommerce_lighting.md) | Lighting retailer — busier, shorter sessions | ~1,365 |
| [`ecommerce_furniture.json`](../docs/presets/ecommerce_furniture.md) | Furniture retailer — quieter, longer sessions | ~415 |
| [`vpc_flow_logs.json`](../docs/presets/vpc_flow_logs.md) | AWS VPC Flow Logs | ~25 |
| [`ssh_auth.json`](../docs/presets/ssh_auth.md) | Linux SSH authentication | ~38 |
| [`pbx_calls.json`](../docs/presets/pbx_calls.md) | PBX call detail records | ~5 |
| [`endpoint_network.json`](../docs/presets/endpoint_network.md) | Internet-facing Windows endpoint network traffic | ~1 |

## Schedules

| Schedule | Description |
| --- | --- |
| `ecommerce.json` | Weekday afternoon peaks, quiet overnight and weekends |
| `full.json` | Flat 1.0 multiplier — equivalent to no schedule |

See [schedule documentation](../docs/schedules.md) for how schedules interact with `-m` and how to write your own.
