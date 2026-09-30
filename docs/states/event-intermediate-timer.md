# `event:intermediate:timer`

A pause between two activities. Use this whenever you need the simulated clock
to advance before the next activity runs—for example, to model the duration of a
network flow, a page dwell time, or a processing delay. It does not emit a
record and cannot set variables.

| Field                      | Description                                                                     | Required? |
| -------------------------- | ------------------------------------------------------------------------------- | --------- |
| `name`                     | Unique name for this state.                                                     | Yes       |
| `type`                     | Must be `"event:intermediate:timer"`.                                           | Yes       |
| `_comment`                 | Optional annotation.                                                            | No        |
| `cardinality_distribution` | How long (in seconds) to delay. A [`distribution`](../distributions.md) object. | Yes       |
| `next`                     | Name of the next state (a string, not a transitions list).                      | Yes       |

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
