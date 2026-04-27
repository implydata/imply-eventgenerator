# Object

Use `object` to produce a nested JSON object. The `dimensions` list inside the object follows the same generated variable rules as a top-level emitter.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `object` |
| `name` | Yes | Field name in the output record. |
| `dimensions` | Yes | List of generated variables that make up the nested object. |
| `cardinality` | No | Number of unique object values to produce. `0` for unconstrained. Default `0`. |
| `cardinality_distribution` | Yes, if `cardinality` > 0 | [Distribution](../distributions.md) that selects which pre-generated object to reuse. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null` instead. Default `0`. |

```json
{
  "name": "location",
  "type": "object",
  "cardinality": 0,
  "dimensions": [
    {"name": "city", "type": "enum", "values": ["London", "Paris", "Berlin"],
     "cardinality_distribution": {"type": "uniform", "min": 0, "max": 2}},
    {"name": "lat", "type": "float",
     "distribution": {"type": "uniform", "min": 48.0, "max": 52.0},
     "cardinality": 0, "precision": 4}
  ]
}
```
