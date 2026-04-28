# event:start:timer

The first state in every config. Controls how fast new workers are spawned — the interarrival interval.

| Field | Description | Required? |
| --- | --- | --- |
| `name` | Unique name for this state. | Yes |
| `type` | Must be `"event:start:timer"`. | Yes |
| `_comment` | Optional annotation. | No |
| `cardinality_distribution` | How long (in seconds) to wait before the worker proceeds. A [`distribution`](../distributions.md) object. | Yes |
| `next` | Name of the next state (a string, not a transitions list). | Yes |

```json
{
  "name": "session_start",
  "type": "event:start:timer",
  "_comment": "New sessions arrive every ~1 second on average",
  "cardinality_distribution": {
    "type": "exponential",
    "mean": 1.0
  },
  "next": "setup_session"
}
```

---

## See also

- [State types index](../states.md)
- [Distributions](../distributions.md) — distribution types for `cardinality_distribution`
