# Synthetic timestamps

When a [field generator](./field-generators.md) type is `timestamp`, an ISO format datetime is produced.

| Field | Description | Possible values | Required? | Default |
| --- | --- | --- | --- | --- |
| `type` | The data type for the dimension. | `timestamp` | Yes | |
| `name` | The unique name for the dimension. | String | Yes | |
| `cardinality` | Indicates the number of unique values for this dimension. Use zero for unconstrained cardinality. | Integer | Yes | |
| `cardinality_distribution` | Skews the cardinality selection of the generated values. | A [distribution](./distributions.md) object. | Yes, if `cardinality` not 0. | |
| `percent_missing` | The stochastic frequency for omitting this dimension from records (inclusive). | Integer between 0 and 100. | No. | 0 |
| `percent_nulls` | The stochastic frequency (inclusive) for generating null values. | Integer between 0 and 100. | No. | 0 |
| `distribution` | Describes the distribution of timestamp values the driver generates, with the dates given in ISO format. | A [distribution](./distributions.md) object. | Yes | |

In this example, `session_start` spawns a new worker every second. A `gateway:exclusive` routes 80% to `example_event_1` and 20% to `example_event_2`, each preceded by a 0.1-second timer, cycling continuously.

The emitter for `state_1` is `example_event_1`. This emits a simple [`string`](./types/string.md) as `emitter_number`, and `timestamp` in the range between 1st January 2020 at 3pm and 1st January 2020 at 8pm. `percent_nulls` adds a 25% chance that the value is null.

The emitter for `state_2` is `example_event_2` which also emits a simple string containing the emitter number. The `timestamp` for these events lie between 1st and 2nd of January 1920.

```json
{
  "states": [
    {
      "name": "session_start",
      "type": "event:start:timer",
      "cardinality_distribution": { "type": "constant", "value": 1 },
      "next": "route_event"
    },
    {
      "name": "route_event",
      "type": "gateway:exclusive",
      "transitions": [
        { "next": "pause_state_1", "probability": 0.8 },
        { "next": "pause_state_2", "probability": 0.2 }
      ]
    },
    {
      "name": "pause_state_1",
      "type": "event:intermediate:timer",
      "cardinality_distribution": { "type": "constant", "value": 0.1 },
      "next": "emit_state_1"
    },
    {
      "name": "emit_state_1",
      "type": "activity",
      "emitter": "example_event_1",
      "next": "route_event"
    },
    {
      "name": "pause_state_2",
      "type": "event:intermediate:timer",
      "cardinality_distribution": { "type": "constant", "value": 0.1 },
      "next": "emit_state_2"
    },
    {
      "name": "emit_state_2",
      "type": "activity",
      "emitter": "example_event_2",
      "next": "route_event"
    }
  ],
  "emitters": [
    {
      "name": "example_event_1",
      "dimensions": [
        {
          "name": "emitter_number",
          "type": "string",
          "chars": "1",
          "length_distribution": { "type": "constant", "value": 1 }, "cardinality": 0
        },
        {
          "name": "timestamp",
          "type": "timestamp",
          "percent_nulls": 25,
          "cardinality": 0,
          "distribution": {
            "type": "uniform",
            "min": "2020-01-01T15:00",
            "max": "2020-01-01T20:00"
          }
        }
      ]
    },
    {
      "name": "example_event_2",
      "dimensions": [
        {
          "name": "emitter_number",
          "type": "string",
          "chars": "2",
          "length_distribution": { "type": "constant", "value": 1 }, "cardinality": 0
        },
        {
          "name": "timestamp",
          "type": "timestamp",
          "percent_nulls": 25,
          "cardinality": 0,
          "distribution": {
            "type": "uniform",
            "min": "1920-01-01",
            "max": "1920-01-02"
          }
        }
      ]
    }
  ]
}
```

Since the JSON above contains an inline `target`, you can save the JSON above as `example.json` and run it with the following command.

```bash
python3 src/generator.py -f example.json -n 15 -m 2 -s "2009-05-21:08:00:10"
```

This is an example of the output:

```json
{"time":"2025-02-17T15:31:27.213","emitter_number":"1","timestamp":"2020-01-01T16:21:26.763"}
{"time":"2025-02-17T15:31:27.323","emitter_number":"1","timestamp":"2020-01-01T19:55:08.589"}
{"time":"2025-02-17T15:31:27.424","emitter_number":"1","timestamp":"2020-01-01T19:08:42.125"}
{"time":"2025-02-17T15:31:27.526","emitter_number":"1","timestamp": null}
{"time":"2025-02-17T15:31:27.632","emitter_number":"1","timestamp":"2020-01-01T19:14:46.070"}
{"time":"2025-02-17T15:31:27.736","emitter_number":"2","timestamp":"1920-01-01T01:04:10.144"}
{"time":"2025-02-17T15:31:27.842","emitter_number":"1","timestamp":"2020-01-01T16:33:39.371"}
{"time":"2025-02-17T15:31:27.945","emitter_number":"2","timestamp":"1920-01-01T17:32:15.567"}
{"time":"2025-02-17T15:31:28.051","emitter_number":"1","timestamp":"2020-01-01T18:25:38.457"}
{"time":"2025-02-17T15:31:28.155","emitter_number":"2","timestamp":"1920-01-01T22:53:57.637"}
```
