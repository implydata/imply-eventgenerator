# Field generators

Field generators are JSON objects that appear in emitter [`dimensions`](./genspec-emitters.md) and state [`variables`](./genspec-states.md).

Whenever a worker encounters a field generator, whether via an emitter dimension list or a state variable, it generates a key (`name`) and a value.

The value that is generated depends on the field generator `type`.

## Field generator types

Available field generator types are:

* [`clock`](#clock) generates a datetime using the simulated clock.
* [`timestamp`](./type-timestamp.md) generates a datetime between a range.
* [`string`](./type-string.md) creates a synthetic string, optionally limited to a specific list of characters.
* [`int`](./type-int.md) generates whole numbers.
* [`float`](./type-float.md) generates floating point numbers.
* [`ipaddress`](./type-ipaddress.md) creates a network IP address.
* [`counter`](./type-counter.md) creates an incrementing integer.
* [`enum`](#enum)
* [`object`](#object)
* [`list`](#list)

### `clock`

Use the `clock`-type field generator to mimic an event timestamp.

Every state machine worker has an internal clock that starts at the time the worker is created by the data generator.

* The very first worker starts either at the current date time, or by using the `-s` argument at the [command line](./command-line.md), at a simulated clock start time.
* The next output event for that worker is emitted based on the `delay` between `states`. For more information, see [`states`](./genspec-states.md).

The data generator spawns additional workers up to a configurable maximum, e.g. using the `-m` argument at the [command line](./command-line.md). The interval between workers being spawned is controlled by the `interarrival` time, set in the [generator specification](./genspec.md).

```bash
python3 src/generator.py -f example.json -n 10 -m 1
```

Clock dimensions have the following structure:

```json
{
  "type": "clock",
  "name": "<dimension name>"
}
```

### `enum`

Enum field generators specify the set of all possible values, as well as a distribution for selecting from the set.

Enums have the following format:

```json
{
  "type": "enum",
  "name": "<dimension name>",
  "values": [...],
  "cardinality_distribution": <distribution descriptor object>,
  "percent_missing": <percentage value>,
  "percent_nulls": <percentage value>
}
```

Where:

* __name__ is the name of the dimension
* __values__ is a list of the values
* __cardinality_distribution__ informs the cardinality selection of the generated values
* __percent_missing__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for omitting this dimension from records (optional - the default value is 0.0 if omitted)
* __percent_nulls__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for generating null values (optional - the default value is 0.0 if omitted)

### `object`

Object field generators create nested data.

* __name__ is the name of the object
* __cardinality__ indicates the number of unique values for this dimension (zero for unconstrained cardinality)
* __cardinality_distribution__ skews the cardinality selection of the generated objects (optional - omit for unconstrained cardinality)
* __percent_missing__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for omitting this dimension from records (optional - the default value is 0.0 if omitted)
* __percent_nulls__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for generating null values (optional - the default value is 0.0 if omitted)
* __dimensions__ is a list of nested dimensions

```json
{
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        {
          "type": "object",
          "name": "Obj1",
          "cardinality": 0,
          "dimensions": [
            {
              "type": "clock",
              "name": "__time"
            },
            {
              "type": "enum",
              "name": "enum_dim",
              "values": ["A", "B", "C"],
              "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
            },
            {
              "type": "string",
              "name": "string_dim",
              "length_distribution": { "type": "constant", "value": 5 },
              "cardinality": 0,
              "chars": "ABC123"
            },
            {
              "type": "int",
              "name": "int_dim",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "exponential", "mean": 5 }
            },
            {
              "type": "float",
              "name": "dim_float",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "normal", "mean": 5, "stddev": 2 },
              "precision": 3
            },
            {
              "type": "timestamp",
              "name": "dim_timestamp",
              "distribution": { "type": "uniform", "min": "2008-09-03T10:00:00.0Z", "max": "2008-09-03T20:00:00.0Z" },
              "cardinality": 0
            },
            {
              "type": "ipaddress",
              "name": "dim_ip",
              "distribution": { "type": "uniform", "min": 2130706433, "max": 2130706440 },
              "cardinality": 0
            }
          ]
        },
        {
          "type": "object",
          "name": "Obj2",
          "cardinality": 3,
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 },
          "dimensions": [
            {
              "type": "clock",
              "name": "__time"
            },
            {
              "type": "enum",
              "name": "enum_dim",
              "values": ["A", "B", "C"],
              "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
            },
            {
              "type": "string",
              "name": "string_dim",
              "length_distribution": { "type": "constant", "value": 5 },
              "cardinality": 0,
              "chars": "ABC123"
            },
            {
              "type": "int",
              "name": "int_dim",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "exponential", "mean": 5 }
            },
            {
              "type": "float",
              "name": "dim_float",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "normal", "mean": 5, "stddev": 2 },
              "precision": 3
            },
            {
              "type": "timestamp",
              "name": "dim_timestamp",
              "distribution": { "type": "uniform", "min": "2008-09-03T10:00:00.0Z", "max": "2008-09-03T20:00:00.0Z" },
              "cardinality": 0
            },
            {
              "type": "ipaddress",
              "name": "dim_ip",
              "distribution": { "type": "uniform", "min": 2130706433, "max": 2130706440 },
              "cardinality": 0
            }
          ]
        }
      ]
    }
  ],
  "interarrival": { "type": "constant", "value": 1 },
  "states": [
    {
      "name": "state_1",
      "emitter": "example_record_1",
      "delay": { "type": "constant", "value": 1 },
      "transitions": [{ "next": "state_1", "probability": 1.0 }]
    }
  ]
}
```

### `list`

list field generators create lists of dimesions.

* __name__ is the name of the object
* __length_distribution__ describes the length of the resulting list as a distribution
* __selection_distribution__ informs the generator which elements to select for the list from the elements list
* __elements__ is a list of possible dimensions the generator may use in the generated list
* __cardinality__ indicates the number of unique values for this dimension (zero for unconstrained cardinality)
* __cardinality_distribution__ skews the cardinality selection of the generated lists (optional - omit for unconstrained cardinality)
* __percent_missing__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for omitting this dimension from records (optional - the default value is 0.0 if omitted)
* __percent_nulls__ a value in the range of 0.0 and 100.0 (inclusive) indicating the stochastic frequency for generating null values (optional - the default value is 0.0 if omitted)

The data generator creates a list that is the length of a sample from the __length_distribution__.

The types of the elements of the list are selected from the __elements__ list by using an index into the elements list that is determined by sampling from the __selection_distribution__.

The other field values (e.g., __cardinality__, __percent_nulls__, etc.) operate like the other types, but in this case apply to the entire list.

```json
{
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        {
          "type": "list",
          "name": "List1",
          "length_distribution": { "type": "uniform", "min": 1, "max": 3 },
          "selection_distribution": { "type": "uniform", "min": 0, "max": 5 },
          "cardinality": 0,
          "elements": [
            {
              "type": "enum",
              "name": "enum_dim",
              "values": ["A", "B", "C"],
              "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
            },
            {
              "type": "string",
              "name": "string_dim",
              "length_distribution": { "type": "constant", "value": 5 },
              "cardinality": 0,
              "chars": "ABC123"
            },
            {
              "type": "int",
              "name": "int_dim",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "exponential", "mean": 5 }
            },
            {
              "type": "float",
              "name": "dim_float",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "normal", "mean": 5, "stddev": 2 },
              "precision": 3
            },
            {
              "type": "timestamp",
              "name": "dim_timestamp",
              "distribution": { "type": "uniform", "min": "2008-09-03T10:00:00.0Z", "max": "2008-09-03T20:00:00.0Z" },
              "cardinality": 0
            },
            {
              "type": "ipaddress",
              "name": "dim_ip",
              "distribution": { "type": "uniform", "min": 2130706433, "max": 2130706440 },
              "cardinality": 0
            }
          ]
        },
        {
          "type": "list",
          "name": "List2",
          "length_distribution": { "type": "uniform", "min": 1, "max": 3 },
          "selection_distribution": { "type": "uniform", "min": 0, "max": 5 },
          "cardinality": 3,
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 },
          "elements": [
            {
              "type": "enum",
              "name": "enum_dim",
              "values": ["A", "B", "C"],
              "cardinality_distribution": { "type": "uniform", "min": 0, "max": 2 }
            },
            {
              "type": "string",
              "name": "string_dim",
              "length_distribution": { "type": "constant", "value": 5 },
              "cardinality": 0,
              "chars": "ABC123"
            },
            {
              "type": "int",
              "name": "int_dim",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "exponential", "mean": 5 }
            },
            {
              "type": "float",
              "name": "dim_float",
              "distribution": { "type": "uniform", "min": 0, "max": 1000 },
              "cardinality": 10,
              "cardinality_distribution": { "type": "normal", "mean": 5, "stddev": 2 },
              "precision": 3
            },
            {
              "type": "timestamp",
              "name": "dim_timestamp",
              "distribution": { "type": "uniform", "min": "2008-09-03T10:00:00.0Z", "max": "2008-09-03T20:00:00.0Z" },
              "cardinality": 0
            },
            {
              "type": "ipaddress",
              "name": "dim_ip",
              "distribution": { "type": "uniform", "min": 2130706433, "max": 2130706440 },
              "cardinality": 0
            }
          ]
        }
      ]
    }
  ],
  "interarrival": { "type": "constant", "value": 1 },
  "states": [
    {
      "name": "state_1",
      "emitter": "example_record_1",
      "delay": { "type": "constant", "value": 1 },
      "transitions": [{ "next": "state_1", "probability": 1.0 }]
    }
  ]
}
```
