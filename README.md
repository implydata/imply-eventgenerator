# Imply event generator

A highly customizable event data generator, created by the team at Imply.

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
| [`-c`](#generator-configuration) | The name of the file in the `config_file` folder containing the [generator configuration](#generator-configuration). |
| [`-t` / `--template`](docs/templates.md) | A named output template embedded in the generator config. Mutually exclusive with `-f`. See [output templates](docs/templates.md). |
| [`-f`](#output-format) | **(Deprecated)** A file that contains a pattern that can be used to format the output records. Use `-t` instead. |
| [`-s`](#simulated-time) | Use a simulated clock starting at the specified ISO time, rather than using the system clock. This will cause records to be produced instantaneously (batch) rather than with a real clock (real-time). |
| [`-m`](#generator-configuration) | The maximum number of workers to create. Defaults to 100. |
| [`-n`](#generation-limits) | The number of records to generate. Must not be used in combination with `-r`. |
| [`-r`](#generation-limits) | The length of time to create records for, expressed in ISO8601 format. Must not be used in combination with `-n`. |
| [`--schedule`](docs/schedules.md) | A JSON file that modulates the number of active workers over time, producing time-of-day traffic variation. See the [schedule documentation](docs/schedules.md) for available schedules and how to write your own. |
| `--debug` | Enable debug logging. Outputs detailed thread scheduling and event queue information to stderr. |
| [`--seed`](docs/deterministic.md) | An integer seed for deterministic data generation. Use with `-s` for fully reproducible output. |

You can also run the generator as an HTTP service. See the [server API reference](docs/server.md) for details.

### Generator configuration

The [generator configuration](docs/generator-config.md) is a JSON document that sets how the data generator will execute. When the `-f` option is used, the generator configuration will be read from a file, otherwise the generator configuration will be read from `stdin`.

A generator configuration follows this structure:

```json
{
  "states": [ ... ],
  "emitters": [ ... ],
  "interarrival": { }
}
```

The sections of the JSON document concern what each data generator worker will do.

* A list of [`states`](docs/states.md) that a worker can transition through.
* A list of [`emitters`](docs/emitters.md), listing the dimensions that will be output by a worker and what data they will contain. Each dimension uses a [field generator](docs/field-generators.md) to produce values, controlled by [distributions](docs/distributions.md).
* The `interarrival` time, controlling how often a new worker is spawned. The default maximum number of workers is 100, unless the `-m` argument is used.

For full details, see the [generator configuration reference](docs/generator-config.md). See also [common patterns](docs/patterns.md) and [best practices](docs/best-practices.md) for building configurations.

### Output format

Configs that include a `templates` block (such as those in `presets/configs/`) support named output templates selected with `--template`. Templates use Jinja2 and can produce JSON, CSV, NCSA combined logs, and more from a single config. See the [output templates reference](docs/templates.md).

For configs without a `templates` block, use `-f` to supply an external format file — a text file with field names in braces (`{{` and `}}`). Format files support datetime formatting and environment variable substitution. See the [format file reference](docs/formats.md).

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
