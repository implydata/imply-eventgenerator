# Clock timestamp

Use `clock` to emit the current simulated clock time as the event timestamp. The value advances with the Actor's position in the state machine — each `sleep()` call on a timer state moves the clock forward.

| Field | Required? | Description |
| --- | --- | --- |
| `type` | Yes | `clock` |
| `name` | Yes | Field name in the output record. |

```json
{"name": "time", "type": "clock"}
```

Unlike other field generators, `clock` does not support `percent_missing` or `percent_nulls` — it is always included in the record.
