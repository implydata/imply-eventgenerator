# Imply event generator

A highly customizable event data generator, created by the team at Imply.

A config is source code. The engine is a runtime. The language has first-class primitives for randomness, time, and concurrency — things no general-purpose language treats as primitive because they are incidental to most programs but central to this one. See [`docs/language.md`](docs/language.md) for the full language feature inventory and roadmap.

## Prerequisites

The data generator requires Python 3.

Create and activate a local virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Quickstart

Run the following example to test the generator script:

```sh
python generator.py -c presets/configs/ecommerce.json -t access_combined -m 1 -n 10
```

This command generates logs in the format of [Apache access combined logs](https://httpd.apache.org/docs/2.4/logs.html).
It uses a single worker to generate 10 records, and it outputs the results to the standard output stream, such as the terminal window. Status messages are written to stderr, so stdout contains only data and can be piped directly.

For more examples and test cases, see [`test.sh`](./test.sh).

The `presets/` folder contains ready-to-use configs with [embedded output templates](docs/templates.md) — use `-t` to select an output format by name. See [presets/README.md](presets/README.md) for details.

## Documentation

**Building your own config?** Start here:

- [How to build a config](docs/how-to-build-a-config.md) — step-by-step from concept to tested config, with a worked example
- [Common patterns](docs/patterns.md) — variable persistence, multi-record sessions, flow duration
- [Best practices](docs/best-practices.md) — naming conventions, the synthetic clock, common pitfalls

**Reference** — field-level lookup for all config options:

- [Language](docs/language.md) — feature inventory, what's implemented and what's planned
- [States](docs/states.md) — all state types and their fields
- [Emitters](docs/emitters.md) — record output configuration
- [Generated variables](docs/variables-generated.md) — all generated variable types
- [Distributions](docs/distributions.md) — uniform, exponential, normal, gmm_temporal
- [Templates](docs/templates.md) — Jinja2 output templates
- [Schedules](docs/schedules.md) — time-of-day traffic variation
- [Deterministic output](docs/deterministic.md) — reproducible generation with `--seed`

## Command-line reference

Run the `generator.py` script from the command line with Python.

```bash
python generator.py \
        -c <generator configuration file> \
        -t <template name> \
        -f <format file> \
        -s <start timestamp> \
        -m <generator workers limit> \
        -n <record limit> \
        -r <duration limit in ISO8610 format> \
        --schedule <schedule file> \
        --debug \
        --seed <integer>
```

| Argument | Description |
| --- | --- |
| [`-c`](#generator-configuration) | Path to the generator configuration JSON file. See [generator configuration reference](docs/generator-config.md). |
| [`-t` / `--template`](docs/templates.md) | A named output template embedded in the generator config. See [output templates](docs/templates.md). |
| [`-s`](#simulated-time) | Use a simulated clock starting at the specified ISO time, rather than using the system clock. This will cause records to be produced instantaneously (batch) rather than with a real clock (real-time). |
| [`-m`](#generator-configuration) | The maximum number of workers to create. Defaults to 100. |
| [`-n`](#generation-limits) | The number of records to generate. Must not be used in combination with `-r`. |
| [`-r`](#generation-limits) | The length of time to create records for, expressed in ISO8601 format. Must not be used in combination with `-n`. |
| [`--schedule`](docs/schedules.md) | A JSON file that modulates the number of active workers over time, producing time-of-day traffic variation. See the [schedule documentation](docs/schedules.md) for available schedules and how to write your own. |
| `--debug` | Enable debug logging. Outputs detailed thread scheduling and event queue information to stderr. |
| [`--seed`](docs/deterministic.md) | An integer seed for deterministic data generation. Use with `-s` for fully reproducible output. |

### Generator configuration

The [generator configuration](docs/generator-config.md) is a JSON document passed via `-c`. It contains two top-level arrays:

```json
{
  "states": [ ... ],
  "emitters": [ ... ]
}
```

- A list of [`states`](docs/states.md) that each worker traverses. The first state controls interarrival pacing; subsequent states set variables, emit records, route between paths, and terminate.
- A list of [`emitters`](docs/emitters.md) that define output record shape. Each dimension either generates a value directly (see [generated variables](docs/variables-generated.md)) or reads from the variable namespace (see [variable](docs/types/variable.md)).

Each concurrent worker (`-m`) runs one independent Actor — one lifecycle from the initial `event:start:timer` to `event:end`. For the full design process, see [how to build a config](docs/how-to-build-a-config.md).

### Output format

Configs that include a `templates` block (such as those in `presets/configs/`) support named output templates selected with `--template`. Templates use Jinja2 and can produce JSON, CSV, NCSA combined logs, and more from a single config. See the [output templates reference](docs/templates.md).

### Generation limits

Use `-n` to stop after a number of records, or `-r` to stop after a duration (ISO 8601). If neither is set, the generator runs indefinitely.

```bash
# 1000 records
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -n 1000

# One hour of data
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -r PT1H
```

### Simulated time

By default, timestamps reflect the real system clock. Use `-s` to start a synthetic clock at a fixed point in time — records are produced instantly rather than in real time, which is recommended for generating large volumes of historical data.

```bash
# 1000 records starting 1 Jan 2025
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -n 1000 -s "2025-01-01T00:00"

# One hour of data starting 1 Jan 2025
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -r PT1H -s "2025-01-01T00:00"
```

## Using the output

The generator always writes to stdout. Pipe it to whatever destination you need.

### stdout

The default — useful for inspection or piping to other tools:

```bash
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -n 100
```

### File

Redirect stdout to a file:

```bash
python generator.py -c presets/configs/ecommerce.json -t apache:access:json -n 1000 > events.json
```

### Apache Kafka

Pipe to [kcat](https://github.com/edenhill/kcat):

```bash
python generator.py -c presets/configs/ecommerce.json -t apache:access:json \
  | kcat -b localhost:9092 -t my-topic
```

### Confluent Cloud

Use kcat with SASL authentication:

```bash
python generator.py -c presets/configs/ecommerce.json -t apache:access:json \
  | kcat -b pkc-example.us-east-1.aws.confluent.cloud:9092 \
         -X security.protocol=SASL_SSL \
         -X sasl.mechanisms=PLAIN \
         -X sasl.username="$CONFLUENT_API_KEY" \
         -X sasl.password="$CONFLUENT_API_SECRET" \
         -t my-topic
```

### Splunk HEC

When the endpoint is able to apply metadata (e.g. `sourcetype`, `index`, and `host`), pipe to `services/collector/raw`:

```bash
python generator.py -c presets/configs/ecommerce.json -t access_combined \
  | curl -s -X POST https://hec.example.com/services/collector/raw \
         -H "Authorization: Splunk $HEC_TOKEN" \
         --data-binary @-
```

For full control over metadata, use a pipeline tool that wraps each event in a HEC envelope — an [OTel Collector](https://opentelemetry.io/docs/collector/) with a Splunk HEC exporter, or Cribl or Vector.
