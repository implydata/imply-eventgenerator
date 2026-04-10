# Static integers

Use `int:static` to emit a fixed literal integer — the same value every time.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `int:static` |
| `name` | Yes | Field name in the output record. |
| `value` | Yes | The literal integer to always emit. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null` instead. Default `0`. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |

```json
{"name": "status", "type": "int:static", "value": 200}
```

Use this instead of the `int` type with a `constant` distribution and `cardinality: 1` — that combination is a workaround for the same outcome.
