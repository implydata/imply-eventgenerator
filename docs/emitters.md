# Event emitters

> Building a new config? See [How to build a config](./how-to-build-a-config.md) for the design process. This page is the emitter field reference.

Emitters define the data that will be created by the data generator when a particular [state](./states.md) is reached.

Define one or more emitters, each with its own dimensions and data configuration.

Each emitter has this structure:

| Field | Description | Possible values | Required? |
| --- | --- | --- | --- |
| `name` | The unique name for the emitter. | | Yes |
| `dimensions` | A list of attributes and measures, and, for each, the configuration for how data will be generated. | | Yes |

Use the `dimensions` list to prescribe the event timestamp, attributes, and measures for each record created by a worker as it enters each state.

Each entry in `dimensions` answers one question: **how should this field get its value?** There are two answers:

- **Generate it directly** — use any [generated variable type](./variables-generated.md) (`clock`, `enum`, `string`, `int`, etc.). The value is produced at emit time and written straight into the output record, without touching the variable namespace.
- **Read it from the namespace** — use `"type": "variable"`. The value is looked up in the worker's variable namespace at emit time. The namespace is written by [generated variables](./variables-generated.md) (activity `variables` block) and by [`subprocess:multi:variables`](./states/subprocess-multi-variables.md) (parent `items` list).

See [states](./states.md) for how variables are written into the namespace.
