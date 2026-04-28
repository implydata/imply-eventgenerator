# activity

An activity is where work happens: variables are evaluated and, optionally, a record is emitted.

**Execution order** within an activity state:

1. `variables` are evaluated (if present).
2. If an `emitter` is specified, a record is emitted using the current variable values.
3. The `next` state is selected.

| Field | Description | Required? |
| --- | --- | --- |
| `name` | Unique name for this state. | Yes |
| `type` | Must be `"activity"`. | Yes |
| `_comment` | Optional annotation. | No |
| `variables` | A list of [generated variables](../variables-generated.md) that write sampled values into the variable namespace. Evaluated before the record is emitted. | No |
| `emitter` | The [emitter](../emitters.md) to use. If omitted, no record is emitted. | No |
| `next` | Name of the next state (a string, not a transitions list). Route to an `event:end` state to terminate. | Yes |

---

## Naming conventions

By convention:

- Activity states that **only set variables** (no emitter) are named `setup_*`.
- Activity states that **emit records** (with or without also setting variables) are named `emit_*`.

There is no type distinction between these two patterns — both use `"type": "activity"`. The naming convention exists purely to make configs easier to read.

---

## Example: setup activity

```json
{
  "name": "setup_session",
  "type": "activity",
  "_comment": "Capture session-level variables before routing",
  "variables": [
    {
      "name": "var_user_id",
      "type": "int",
      "cardinality": 0,
      "distribution": { "type": "uniform", "min": 1, "max": 10000 }
    },
    {
      "name": "var_start",
      "type": "clock"
    }
  ],
  "next": "route_session"
}
```

---

## Example: emit activity

```json
{
  "name": "emit_flow_record",
  "type": "activity",
  "_comment": "Capture end time and stats, then emit the completed flow record",
  "variables": [
    { "name": "var_end", "type": "clock" },
    {
      "name": "var_bytes",
      "type": "int",
      "cardinality": 0,
      "distribution": { "type": "uniform", "min": 500, "max": 50000 }
    }
  ],
  "emitter": "flow_log",
  "next": "session_end"
}
```

---

## See also

- [State types index](../states.md)
- [Generated variables](../variables-generated.md) — variable types for use in `variables`
- [Emitters](../emitters.md) — emitter structure and dimension fields
- [Common patterns](../patterns.md) — including the setup → timer → emit pattern for events with duration
