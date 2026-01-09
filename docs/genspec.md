# Generator specifications

Control the behavior of the data generator using a JSON configuration object known as the "Generator Specification". See the `config_file` folder for [examples](../config_file/examples).

Workers traverse a number of [`states`](./genspec-states.md) and generate events as they go using [`emitters`](./genspec-emitters.md). States may optionally omit an emitter to create non-emitting states useful for routing, delays, or variable setup. Workers are created periodically, according to the [`interarrival`](./genspec-interarrival.md) time.

| Object | Description | Options | Required? |
| --- | --- | --- | --- |
| [`states`](./genspec-states.md) | A list of states that will be used to generate events. | See [`states`](./genspec-states.md) | Yes |
| [`emitters`](./genspec-emitters.md) | A list of emitters. | See [`emitters`](./genspec-emitters.md) | Yes |
| [`target`](./tarspec.md) | A target specification. | See [`targets`](./tarspec.md) | No |
| `interarrival` | The period of time that elapses before the next worker is started. | A [distribution](./distributions.md) object. | Yes |

In this example, there is just one state: `state_1`. When each worker reaches that state, it uses the `example_record_1` emitter to produce an event with one field called `enum_dim`, where the possible values of that field are selected using a uniform distribution from a list of characters. `target` provides an inline [target specification](./tarspec.md), causing the output to be sent to `stdout`.

There is then a `delay` of 5 seconds before a worker picks the next state from a list of possible `transitions`. In this specification, because the `next` state is the same as the current state, the worker repeatedly enters this state until the generator itself stops.

The `interarrival` distribution is a `constant`, causing new workers to be spawned once every second.

```json
{
  "states": [
    {
      "name": "state_1",
      "emitter": "example_record_1",
      "delay": {
        "type": "constant",
        "value": 5
      },
      "transitions": [
        {
          "next": "state_1",
          "probability": 1
        }
      ]
    }
  ],
  "emitters": [
    {
      "name": "example_record_1",
      "dimensions": [
        {
          "type": "enum",
          "name": "enum_dim",
          "values": [
            "A",
            "B",
            "C"
          ],
          "cardinality_distribution": {
            "type": "uniform",
            "min": 0,
            "max": 2
          }
        }
      ]
    }
  ],
  "target": { "type" : "stdout"},
  "interarrival": { "type": "constant", "value": 1 }
}
```

Try this out by saving the above to `example.json`.

The following command will create 10 records and use only one worker:

```bash
python3 src/generator.py -f example.json -n 10 -m 1
```

This causes the following output.  Notice that each row is spaced 5 seconds apart, since only one worker is generating results.

```json
{"time":"2025-02-18T09:32:16.416","enum_dim":"A"}
{"time":"2025-02-18T09:32:21.426","enum_dim":"C"}
{"time":"2025-02-18T09:32:26.429","enum_dim":"B"}
{"time":"2025-02-18T09:32:31.434","enum_dim":"C"}
{"time":"2025-02-18T09:32:36.440","enum_dim":"B"}
{"time":"2025-02-18T09:32:41.444","enum_dim":"C"}
{"time":"2025-02-18T09:32:46.449","enum_dim":"B"}
{"time":"2025-02-18T09:32:51.453","enum_dim":"A"}
{"time":"2025-02-18T09:32:56.459","enum_dim":"A"}
{"time":"2025-02-18T09:33:01.464","enum_dim":"B"}
```

When run with the `-m 3`, 3 workers are spawned. Since `interarrival` is a `constant` of 1 second, one worker is spawned every second, meaning that rows 1 through 3 are each from different worker threads, and rows 4 through 6 are those workers in their second state, 7 through 9 in their third state, and so on.

```json
{"time":"2025-02-18T09:35:49.618","enum_dim":"A"}
{"time":"2025-02-18T09:35:50.623","enum_dim":"B"}
{"time":"2025-02-18T09:35:51.629","enum_dim":"C"}
{"time":"2025-02-18T09:35:54.626","enum_dim":"B"}
{"time":"2025-02-18T09:35:55.626","enum_dim":"C"}
{"time":"2025-02-18T09:35:56.635","enum_dim":"A"}
{"time":"2025-02-18T09:35:59.632","enum_dim":"A"}
{"time":"2025-02-18T09:36:00.627","enum_dim":"C"}
{"time":"2025-02-18T09:36:01.640","enum_dim":"A"}
{"time":"2025-02-18T09:36:04.635","enum_dim":"A"}
```
