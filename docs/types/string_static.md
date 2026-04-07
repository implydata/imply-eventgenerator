# Static strings

Use `string:static` to emit a fixed literal string — the same value every time.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `string:static` |
| `name` | Yes | Field name in the output record. |
| `value` | Yes | The literal string to always emit. |
| `percent_nulls` | No | Frequency (0–100) for emitting `null` instead. Default `0`. |
| `percent_missing` | No | Frequency (0–100) for omitting the field entirely. Default `0`. |

```json
{"name": "ident", "type": "string:static", "value": "-"}
```

Use this instead of the `string` type with `chars`, `length_distribution: constant(1)`, and `cardinality: 0` — that combination is a workaround for the same outcome.
