# Worker variables

Use `variable` in an emitter's `dimensions` list to output the current value of a worker variable that was set by an earlier activity state.

**Context restriction**: `variable` is only valid in emitter `dimensions`. Using it in a state's `variables` list (where field generators are used to *set* variables) causes a validation error.

**Runtime error**: if the referenced variable has not been set by the time the emitter runs, the generator raises a `KeyError`. This is not always caught by `--validate` — if the execution path can reach the emitter before the activity that sets the variable, the error will only appear at runtime. Always set variables in a `setup_*` activity that runs before any emit state that references them.

| Field | Description | Possible values | Required? | Default |
| --- | --- | --- | --- | --- |
| `type` | The data type for the dimension. | `variable` | Yes | |
| `name` | The unique name for the dimension. | String | Yes | |
| `variable` | The name of a worker variable set in an activity state's `variables` list. | String | Yes | |

In the following example, `session_start` spawns a new worker every 0.2 seconds. A `setup_session` activity sets `var_client_ip` and `var_account_code` once per session and emits an initial click. A `gateway:exclusive` then routes 70% of the time to another click (after a 1-second pause) and 30% to `session_end`.

Both activities use the `click` emitter, which contains:

* An `enum` dimension to randomly output a request URL.
* The value of the `var_client_ip` variable, output as the `client_ip` field.
* The value of the `var_account_code` variable, output as the `account_code` field.

```json
{
  "states": [
    {
      "name": "session_start",
      "type": "event:start:timer",
      "cardinality_distribution": { "type": "constant", "value": 0.2 },
      "next": "setup_session"
    },
    {
      "name": "setup_session",
      "type": "activity",
      "emitter": "click",
      "variables": [
        {
          "name": "var_client_ip",
          "type": "ipaddress",
          "cardinality": 5,
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 5 },
          "distribution": { "type": "uniform", "min": 184549376, "max": 2127008767 }
        },
        {
          "name": "var_account_code",
          "type": "string",
          "length_distribution": { "type": "constant", "value": 5 },
          "cardinality": 0,
          "chars": "ABC123"
        }
      ],
      "next": "route_continue"
    },
    {
      "name": "route_continue",
      "type": "gateway:exclusive",
      "transitions": [
        { "next": "pause_click", "probability": 0.7 },
        { "next": "session_end", "probability": 0.3 }
      ]
    },
    {
      "name": "pause_click",
      "type": "event:intermediate:timer",
      "cardinality_distribution": { "type": "constant", "value": 1 },
      "next": "emit_click"
    },
    {
      "name": "emit_click",
      "type": "activity",
      "emitter": "click",
      "next": "route_continue"
    },
    {
      "name": "session_end",
      "type": "event:end"
    }
  ],
  "emitters": [
    {
      "name": "click",
      "dimensions": [
        { "name": "time", "type": "clock" },
        { "name": "client_ip", "type": "variable", "variable": "var_client_ip" },
        { "name": "account_code", "type": "variable", "variable": "var_account_code" },
        {
          "name": "request",
          "type": "enum",
          "values": [
            "GET /api/articles",
            "GET /api/articles/42",
            "GET /api/articles/102/history",
            "GET /api/articles/56/contributors",
            "GET /api/categories",
            "GET /api/categories/7/articles",
            "GET /api/search?q=quantum-mechanics",
            "GET /api/users/18",
            "GET /api/users/73/contributions",
            "GET /api/recent-changes"
          ],
          "cardinality_distribution": { "type": "uniform", "min": 0, "max": 9 }
        }
      ]
    }
  ]
}
```

Save the JSON above as `example.json` and run it with the following command.

```bash
python generator.py -c example.json -n 15 -m 2 -s "2009-05-21T08:00:10"
```

* `-n 15` specifies a maximum of 15 records.
* `-m 2` sets a maximum of 2 workers.
* `-s` instructs the data generator to use a simulated clock.

Here is an example of the output:

```json
{"time":"2009-05-21T08:00","client_ip":"57.222.36.183","account_code":"A3332","request":"GET /api/articles/56/contributors"}
{"time":"2009-05-21T08:00:10.200","client_ip":"96.8.91.108","account_code":"BA113","request":"GET /api/users/18"}
{"time":"2009-05-21T08:00:10.500","client_ip":"57.222.36.183","account_code":"A3332","request":"GET /api/categories/7/articles"}
{"time":"2009-05-21T08:00:10.700","client_ip":"96.8.91.108","account_code":"BA113","request":"GET /api/articles/42"}
{"time":"2009-05-21T08:00:11.500","client_ip":"57.222.36.183","account_code":"A3332","request":"GET /api/articles/102/history"}
{"time":"2009-05-21T08:00:11.700","client_ip":"96.8.91.108","account_code":"BA113","request":"GET /api/users/73/contributions"}
{"time":"2009-05-21T08:00:12.500","client_ip":"57.222.36.183","account_code":"A3332","request":"GET /api/categories/7/articles"}
{"time":"2009-05-21T08:00:15.400","client_ip":"121.93.131.111","account_code":"2A2AC","request":"GET /api/search?q=quantum-mechanics"}
{"time":"2009-05-21T08:00:15.600","client_ip":"58.116.85.49","account_code":"BA221","request":"GET /api/users/73/contributions"}
{"time":"2009-05-21T08:00:15.900","client_ip":"121.93.131.111","account_code":"2A2AC","request":"GET /api/users/18"}
{"time":"2009-05-21T08:00:16.100","client_ip":"58.116.85.49","account_code":"BA221","request":"GET /api/categories"}
{"time":"2009-05-21T08:00:17.100","client_ip":"58.116.85.49","account_code":"BA221","request":"GET /api/articles"}
{"time":"2009-05-21T08:00:20.800","client_ip":"50.142.218.94","account_code":"1B3B3","request":"GET /api/categories"}
{"time":"2009-05-21T08:00","client_ip":"83.237.12.225","account_code":"1BB3B","request":"GET /api/articles/56/contributors"}
{"time":"2009-05-21T08:00:21.300","client_ip":"50.142.218.94","account_code":"1B3B3","request":"GET /api/articles/42"}
```
