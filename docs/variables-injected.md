# Variables — injected

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page covers how values flow from a parent `subprocess:multi_instance` state into the child's variable namespace.

The variable namespace is a per-worker dict that persists for the lifetime of each worker lifecycle. Injected variables are values written into that namespace by the parent, for each iteration of a `subprocess:multi_instance` state. The other way to write to the namespace is via [generated variables](./variables-generated.md).

---

## How injection works

Each item in the parent's `in` list is a list of variable specs — the same format as a `variables` block in an `activity` state. The engine parses them at startup and evaluates them at runtime using the standard variable generation path.

For each iteration, the engine evaluates that iteration's variable specs and writes the results into the namespace before running the child state machine from its `event:start:message` entry point.

```json
{
  "name": "load_components",
  "type": "subprocess:multi_instance",
  "items": [
    [{"name": "url", "type": "string:static", "value": "/index.html"}, {"name": "bytes", "type": "int:static", "value": 1247}],
    [{"name": "url", "type": "string:static", "value": "/static/style.css"}, {"name": "bytes", "type": "int:static", "value": 8432}],
    [{"name": "url", "type": "string:static", "value": "/static/app.js"}, {"name": "bytes", "type": "int:static", "value": 42180}]
  ],
  "states": "presets/configs/child.json",
  "next": "emit_end"
}
```

Each inner list is one iteration's variable block. Any generator type valid in a `variables` block is valid here — `string:static`, `int:static`, `enum`, and so on. The child reads the injected values via `"type": "variable"` in its emitter dimensions.

---

## Child config entry point

A child config designed for subprocess use declares `event:start:message` as its first state instead of `event:start:timer`. This is the BPMN Message Start Event — it signals that this config expects to receive variables from a parent rather than starting independently.

```json
{"name": "init", "type": "event:start:message", "next": "load_delay"}
```

The `event:start:message` state can also have a `variables` block for standalone defaults. When called as a subprocess, the parent's injected values are written into the namespace before the `event:start:message` variables block runs, so the parent always wins on any overlapping names.

A config with only `event:start:message` and no `event:start:timer` will fail standalone validation — which is correct and expected for subprocess-only configs.

---

## Reading injected values

To emit an injected value in a record, use `"type": "variable"` in an emitter dimension:

```json
{"name": "url", "type": "variable", "variable": "url"}
```

See [emitters](./emitters.md) for the full emitter dimension reference.
