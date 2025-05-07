## Event emitters

Emitters define the data that will be created by the data generator when a particular [state](./genspec-states.md) is reached.

Define one or more emitters, each with its own dimensions and data specification.

Each emitter has this structure:

| Field | Description | Possible values | Required? |
|---|---|---|---|
| `name` | The unique name for the emitter. | | Yes |
| `dimensions` | A list of attributes and measures, and, for each, the specification for how data will be generated. | | Yes |

Use the `dimensions` list to prescribe the event timestamp, attributes, and measures for each record created by a worker as it enters each state.

The `dimensions` list is made up of [field generators](./fieldgen.md) and, optionally, [worker variables](./type-variable.md).

To understand how to create worker variables, see [states](./genspec-states.md).