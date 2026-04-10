# Synthetic counters

When a [field generator](./field-generators.md) type is `counter`, an integer is created that increments with every generation.

**Counter scope**: each counter is per-worker and per-emitter-dimension-instance. Counters reset to `start` when a new worker lifecycle begins. If a worker visits an emit state multiple times in a single lifecycle, the counter increments on every visit. Two emitters that each define a counter are independent of each other — they do not share state.

Counters are not incremented when the field is missing or null (i.e. `percent_missing` or `percent_nulls` fires).

| Field | Description | Possible values | Required? | Default |
| --- | --- | --- | --- | --- |
| `type` | The data type for the dimension. | `counter` | Yes | |
| `name` | The unique name for the dimension. | String | Yes | |
| `percent_missing` | The stochastic frequency for omitting this dimension from records (inclusive). | Integer between 0 and 100. | No. | 0 |
| `percent_nulls` | The stochastic frequency (inclusive) for generating null values. | Integer between 0 and 100. | No. | 0 |
| `start` | The starting value for the counter. | Integer | No. | 0 |
| `increment` | The increment for the counter. | Integer | No. | 1 |

In this example, `session_start` spawns a new worker every second. A `gateway:exclusive` routes 50/50 between two emitters — each preceded by a 0.1-second timer — cycling continuously.

Each state has its own emitter, `state_1` uses `example_event_1`, `state_2` uses `example_event_2`.

The first emitter, `example_event_1`, contains four counter dimensions:

* `default_counter1` uses all defaults, starting at 0 and incrementing by 1.
* `start_counter1` begins at 100, and uses the default increment of 1.
* `increment_counter1` uses the default start of 0, but has a specific increment of 10000.
* `both_counter1` uses both a specific start and increment, 250 and 50 respectively.

The second emitter, `example_event_2`, mirrors the same configuration, using different dimension names and different start and increment values.

```json
{
  "states": [
    {
      "name": "session_start",
      "type": "event:start:timer",
      "cardinality_distribution": { "type": "constant", "value": 1 },
      "next": "route_emitter"
    },
    {
      "name": "route_emitter",
      "type": "gateway:exclusive",
      "transitions": [
        { "next": "pause_state_1", "probability": 0.5 },
        { "next": "pause_state_2", "probability": 0.5 }
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
      "next": "route_emitter"
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
      "next": "route_emitter"
    }
  ],
  "emitters": [
    {
      "name": "example_event_1",
      "dimensions": [
        { "name": "time", "type": "clock" },
        { "name": "default_counter1", "type": "counter" },
        { "name": "start_counter1", "type": "counter", "start": 100 },
        { "name": "increment_counter1", "type": "counter", "increment": 10000 },
        { "name": "both_counter1", "type": "counter", "start": 250, "increment": 50 }
      ]
    },
    {
      "name": "example_event_2",
      "dimensions": [
        { "name": "time", "type": "clock" },
        { "name": "default_counter2", "type": "counter" },
        { "name": "start_counter2", "type": "counter", "start": 500 },
        { "name": "increment_counter2", "type": "counter", "increment": 50000 },
        { "name": "both_counter2", "type": "counter", "start": 750, "increment": 50 }
      ]
    }
  ]
}
```

Save the above configuration as `example.json` and use the following command to create 10 records with one worker using a simulated clock:

```bash
python generator.py -c example.json -n 10 -m 1 -s "2024-01-01T00:00:00"
```

This is an example of the output using one worker.

```json
{"time":"2025-02-18T10:04:12.637","default_counter1":"0","start_counter1":"100","increment_counter1":"0","both_counter1":"250"}
{"time":"2025-02-18T10:04:12.742","default_counter1":"1","start_counter1":"101","increment_counter1":"10000","both_counter1":"300"}
{"time":"2025-02-18T10:04:12.846","default_counter2":"0","start_counter2":"500","increment_counter2":"0","both_counter2":"750"}
{"time":"2025-02-18T10:04:12.950","default_counter1":"2","start_counter1":"102","increment_counter1":"20000","both_counter1":"350"}
{"time":"2025-02-18T10:04:13.053","default_counter2":"1","start_counter2":"501","increment_counter2":"50000","both_counter2":"800"}
{"time":"2025-02-18T10:04:13.157","default_counter1":"3","start_counter1":"103","increment_counter1":"30000","both_counter1":"400"}
{"time":"2025-02-18T10:04:13.260","default_counter2":"2","start_counter2":"502","increment_counter2":"100000","both_counter2":"850"}
{"time":"2025-02-18T10:04:13.366","default_counter1":"4","start_counter1":"104","increment_counter1":"40000","both_counter1":"450"}
{"time":"2025-02-18T10:04:13.471","default_counter1":"5","start_counter1":"105","increment_counter1":"50000","both_counter1":"500"}
{"time":"2025-02-18T10:04:13.575","default_counter2":"3","start_counter2":"503","increment_counter2":"150000","both_counter2":"900"}
{"time":"2025-02-18T10:04:13.680","default_counter2":"4","start_counter2":"504","increment_counter2":"200000","both_counter2":"950"}
{"time":"2025-02-18T10:04:13.785","default_counter2":"5","start_counter2":"505","increment_counter2":"250000","both_counter2":"1000"}
{"time":"2025-02-18T10:04:13.888","default_counter1":"6","start_counter1":"106","increment_counter1":"60000","both_counter1":"550"}
{"time":"2025-02-18T10:04:13.990","default_counter1":"7","start_counter1":"107","increment_counter1":"70000","both_counter1":"600"}
{"time":"2025-02-18T10:04:14.095","default_counter1":"8","start_counter1":"108","increment_counter1":"80000","both_counter1":"650"}
```
