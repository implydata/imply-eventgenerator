# `event:start:timer`

The first state in every config. Its sole job is to control how fast new workers
are spawned (the interarrival interval). It does not emit a record and cannot
set variables.

Its `cardinality_distribution` can be overridden at runtime without editing the
config, via `-i <seconds>`—supported for `constant` (overrides `value`),
`exponential` and `normal` (overrides `mean`), and `gmm_temporal` (overrides the
base `mean`, leaving its time-of-day shape untouched). Unsupported types (for
example, `uniform`) raise an error rather than silently no-op. See the
[command-line reference](../../README.md#command-line-reference).

| Field                      | Description                                                                                                   | Required? |
| -------------------------- | ------------------------------------------------------------------------------------------------------------- | --------- |
| `name`                     | Unique name for this state.                                                                                   | Yes       |
| `type`                     | Must be `"event:start:timer"`.                                                                                | Yes       |
| `_comment`                 | Optional annotation.                                                                                          | No        |
| `cardinality_distribution` | Time (in seconds) between the starts of consecutive sessions. A [`distribution`](../distributions.md) object. | Yes       |
| `next`                     | Name of the next state (a string, not a transitions list).                                                    | Yes       |

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

## See also

- [State types](../states.md)—all state types, and behavior they share
- [Distributions](../distributions.md)—distribution types for
  `cardinality_distribution`
- [`event:intermediate:timer`](./event-intermediate-timer.md)—the timer that
  delays a session partway through
