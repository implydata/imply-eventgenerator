# event:intermediate:timer

Pauses the worker for a duration sampled from `cardinality_distribution`, advancing the clock. Without `-s`, the thread sleeps on the wall clock. Use this to model the duration of a network flow, a page dwell time, or a processing delay.

| Field | Description | Required? |
| --- | --- | --- |
| `name` | Unique name for this state. | Yes |
| `type` | Must be `"event:intermediate:timer"`. | Yes |
| `_comment` | Optional annotation. | No |
| `cardinality_distribution` | How long (in seconds) to delay. A [`distribution`](../distributions.md) object. | Yes |
| `next` | Name of the next state (a string, not a transitions list). | Yes |

```json
{
  "name": "pause_flow_duration",
  "type": "event:intermediate:timer",
  "_comment": "Flow lasts 5–30 seconds",
  "cardinality_distribution": {
    "type": "uniform",
    "min": 5.0,
    "max": 30.0
  },
  "next": "emit_flow_record"
}
```

---

## See also

- [State types index](../states.md)
- [Distributions](../distributions.md) — distribution types for `cardinality_distribution`
- [activity](./activity.md) — the state that follows a timer to emit records
