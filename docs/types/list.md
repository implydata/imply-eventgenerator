# List

Use `list` to produce an array of values. The generator samples a length from `length_distribution`, then picks that many elements from `elements` using `selection_distribution` as an index.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `list` |
| `name` | Yes | Field name in the output record. |
| `length_distribution` | Yes | [Distribution](../distributions.md) controlling how many elements the list contains. |
| `selection_distribution` | Yes | [Distribution](../distributions.md) that picks an index into `elements` for each slot. |
| `elements` | Yes | List of field generator definitions to draw from. |
| `cardinality` | No | Number of unique list values to produce. `0` for unconstrained. Default `0`. |
| `cardinality_distribution` | Yes, if `cardinality` > 0 | [Distribution](../distributions.md) that selects which pre-generated list to reuse. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null` instead. Default `0`. |

```json
{
  "name": "tags",
  "type": "list",
  "length_distribution": {"type": "uniform", "min": 1, "max": 3},
  "selection_distribution": {"type": "uniform", "min": 0, "max": 2},
  "cardinality": 0,
  "elements": [
    {"name": "tag", "type": "enum", "values": ["sale", "new", "featured"],
     "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}}
  ]
}
```
