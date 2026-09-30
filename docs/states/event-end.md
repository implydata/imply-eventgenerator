# `event:end`

Terminates the worker. No fields other than `name` and `type` are permitted. The
worker exits cleanly after reaching this state.

| Field  | Description                 | Required? |
| ------ | --------------------------- | --------- |
| `name` | Unique name for this state. | Yes       |
| `type` | Must be `"event:end"`.      | Yes       |

```json
{
  "name": "session_end",
  "type": "event:end"
}
```

Every config must have at least one `event:end` state. Configs with multiple
exit paths may have multiple `event:end` states—one per terminal path is valid.
All paths through the state machine must eventually route to an `event:end`.
