# Synthetic strings

When a [field generator](./field-generators.md) type is  `string`, a random string is created.

| Field | Description | Possible values | Required? | Default |
| --- | --- | --- | --- | --- |
| `type` | The data type for the dimension. | `string` | Yes | |
| `name` | The unique name for the dimension. | String | Yes | |
| `cardinality` | Indicates the number of unique values for this dimension. Use zero for unconstrained cardinality. | Integer | Yes | |
| `cardinality_distribution` | Skews the cardinality selection of the generated values. | A [distribution](./distributions.md) object. | Yes, if `cardinality` not 0. | |
| `percent_missing` | The stochastic frequency for omitting this dimension from records (inclusive). | Integer between 0 and 100. | No. | 0 |
| `percent_nulls` | The stochastic frequency (inclusive) for generating null values. | Integer between 0 and 100. | No. | 0 |
| `chars` | A list of characters to use to generate strings. | String | No | All printable characters. |
| `length_distribution` | A distribution function that specifies the length of the string values. | A [distribution](./distributions.md) object. | Yes. | |

In this example, `session_start` spawns a new worker every second. A `gateway:exclusive` routes 20% to `example_event_1`, 50% to `example_event_2`, and 30% to `example_event_3`, each path preceded by a 0.1-second timer, cycling continuously.

The emitter for `state_1` is `example_event_1`. This emits two synthetic strings:

* `account_id` is a synthetic string generated from a string containing the numbers 0 through 9. The maximum length is defined by a `constant` `length_distribution` [distribution](./distributions.md) object, resulting in strings that are always 5 characters long.
* `silly_name` generates a synthetic string with a length defined by a `uniform` `length_distribution` resulting in lengths between 1 and 40. As there is no `chars` specified, it is generated from all printable characters.

The emitter for `state_2` is `example_event_2`. Only the definition of `silly_name` differs. Here, `chars` contains all lower-case characters, and the `length_distribution` results in lengths between 1 and 15 characters.

The emitter for `state_3` is `example_event_3`, and here only upper-case characters are used.

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
        { "next": "pause_state_1", "probability": 0.2 },
        { "next": "pause_state_2", "probability": 0.5 },
        { "next": "pause_state_3", "probability": 0.3 }
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
    },
    {
      "name": "pause_state_3",
      "type": "event:intermediate:timer",
      "cardinality_distribution": { "type": "constant", "value": 0.1 },
      "next": "emit_state_3"
    },
    {
      "name": "emit_state_3",
      "type": "activity",
      "emitter": "example_event_3",
      "next": "route_emitter"
    }
  ],
  "emitters": [
    {
      "name": "example_event_1",
      "dimensions": [
        {
          "name": "account_id",
          "type": "string",
          "chars": "1234567890",
          "length_distribution": { "type": "constant", "value": 5 }, "cardinality": 0
        },
        {
          "name": "silly_name",
          "type": "string",
          "length_distribution": { "type": "uniform", "min": 1, "max": 40 }, "cardinality": 0
        }
      ]
    },
    {
      "name": "example_event_2",
      "dimensions": [
        {
          "name": "account_id",
          "type": "string",
          "chars": "1234567890",
          "length_distribution": { "type": "constant", "value": 5 }, "cardinality": 0
        },
        {
          "name": "silly_name",
          "type": "string",
          "chars": "abcdefghijklmnopqrstuvwxyz",
          "length_distribution": { "type": "uniform", "min": 1, "max": 15 }, "cardinality": 0
        }
      ]
    },
    {
      "name": "example_event_3",
      "dimensions": [
        {
          "name": "account_id",
          "type": "string",
          "chars": "1234567890",
          "length_distribution": { "type": "constant", "value": 5 }, "cardinality": 0
        },
        {
          "name": "silly_name",
          "type": "string",
          "chars": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
          "length_distribution": { "type": "uniform", "min": 1, "max": 15 }, "cardinality": 0
        }
      ]
    }
  ]
}
```

Save the configuration above as `example.json` and use the following command to create 10 records with one worker:

```bash
python3 src/generator.py -f example.json -n 10 -m 1
```

This is an example of the output:

```json
{"time":"1998-04-13T00:00","account_id":"78683","silly_name":"
 *cseAFm"}t-RM
{"time":"1998-04-13T00:00:00.100","account_id":"25423","silly_name":"UTJSIDNJWIIQYZD"}
{"time":"1998-04-13T00:00:00.200","account_id":"55913","silly_name":"vapsfgxqnpzxf"}
{"time":"1998-04-13T00:00:00.300","account_id":"24441","silly_name":"rih"}
{"time":"1998-04-13T00:00:00.400","account_id":"94118","silly_name":"ka"}
{"time":"1998-04-13T00:00:00.500","account_id":"15068","silly_name":"DYYWUOQQGIYWR"}
{"time":"1998-04-13T00:00:00.600","account_id":"60283","silly_name":"mzdmryjfdrck"}
{"time":"1998-04-13T00:00:00.700","account_id":"50914","silly_name":"QJAAW"}
{"time":"1998-04-13T00:00:00.800","account_id":"92367","silly_name":"UHGCBAMYLPXXNNG"}
{"time":"1998-04-13T00:00:00.900","account_id":"84955","silly_name":"elaglicenhwn"}
```
