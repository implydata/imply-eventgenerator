# Enum

Use `enum` to select a value from a fixed list. The `cardinality_distribution` samples an index into `values`; if the sampled index exceeds the list length it is clamped to the last element.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `enum` |
| `name` | Yes | Field name in the output record. |
| `values` | Yes | List of possible values to select from. |
| `cardinality_distribution` | Yes | [Distribution](.../../distributions.md) that picks an index into `values`. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null` instead. Default `0`. |

```json
{
  "name": "method",
  "type": "generator:enum",
  "values": ["GET", "POST", "PUT", "DELETE"],
  "cardinality_distribution": {"type": "uniform", "min": 0, "max": 3}
}
```
