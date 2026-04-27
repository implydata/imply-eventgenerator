# Variables — injected

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page covers subprocess injection — the mechanism that writes values directly into the variable namespace before a child run.

The variable namespace is a per-worker dict that persists for the lifetime of each worker lifecycle. Injected variables are values written into that namespace directly by the parent, before each iteration of a `subprocess:multi_instance` state. The other way to write to the namespace is via [generated variables](./variables-generated.md).

---

## Subprocess injection

When a `subprocess:multi_instance` state iterates over its `in` list, each item is injected into the shared namespace before that iteration's child run. This is runtime injection — the value changes on every iteration.

- **Scalar item** → written as `variables['item'] = item`
- **Object item** → each key is merged: `variables.update(item)`

The child config reads the injected value via `"type": "variable"` in its emitter dimensions. The child is responsible for knowing what keys the parent will inject — it is designed for subprocess use. If standalone use is needed, the engineer adds an initial `setup_*` activity state that sets appropriate defaults in the usual way.

```json
{
  "name": "loop_section",
  "type": "subprocess:multi_instance",
  "in": [1, 2, 3, 4, 5],
  "states": "presets/configs/child.json",
  "next": "emit_end"
}
```

Each iteration injects the current item into the namespace before the child state machine starts. The child sees `item` as if it were set by an initial activity state.

---

## Reading injected values

To emit an injected value in a record, use `"type": "variable"` in an emitter dimension:

```json
{"name": "item", "type": "variable", "variable": "item"}
```

See [emitters](./emitters.md) for the full emitter dimension reference.
