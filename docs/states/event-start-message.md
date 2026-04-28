# event:start:message

The entry point for a child config designed for subprocess use. It is the BPMN **Message Start Event** — triggered by the parent passing in a variables package rather than by an independent timer. A config that declares `event:start:message` signals that it expects to receive values from a [`subprocess:multi:variables`](./subprocess-multi-variables.md) parent.

| Field | Description | Required? |
| --- | --- | --- |
| `name` | Unique name for this state. | Yes |
| `type` | Must be `"event:start:message"`. | Yes |
| `_comment` | Optional annotation. | No |
| `variables` | Optional list of [generated variables](../variables-generated.md). Useful for declaring standalone defaults. The parent's `items` values are written into the namespace before this block runs, so the parent always wins on overlapping names. | No |
| `next` | Name of the next state. | Yes |

```json
{
  "name": "init",
  "type": "event:start:message",
  "next": "load_delay"
}
```

A config with `event:start:message` but no `event:start:timer` will fail standalone validation. That is correct and expected — it is a subprocess-only config. Engineers who need the same config to work standalone add an `event:start:timer` entry point and a `setup_*` activity state with appropriate defaults.

---

## See also

- [State types index](../states.md)
- [subprocess:multi:variables](./subprocess-multi-variables.md) — the parent state that triggers this entry point
- [Generated variables](../variables-generated.md) — variable types for use in the optional `variables` block
