# Imply event generator

A highly customizable event data generator, created by the team at Imply.

## Run from the command line

Run the `generator.py` script from the command line to create synthetic data in JSON format.

```bash
python generator.py \
        -c <generator specification file> \
        -m <generator workers limit> \
        -t <target specification file> \
        -s <start timestamp> \
        -n <record limit> \
        -r <duration limit> \
        -p <pattern specification file>
```

| Argument | Description |
|---|---|
| [`-c`](#generator-specification) | The name of the file in the `config_file` folder containing the [generator specification](#generator-specification).|
| [`-t`](#target-specification) | The name of the file that contains the [target definition](#target.md). This over-rides any `target` specified in the generator specification. If neither is provided, stdout will be used. |
| [`-f`](#record-format) | A file that contains a pattern that can be used to format the output records. If not specified, JSON is used. |
| [`-s`](#simulated-clock) | Use a simulated clock starting at the specified ISO time, rather than using the system clock. This will cause records to be produced instantaneously (batch) rather than with a real clock (real-time). |
| [`-m`](#generator-specification) | The maximum number of workers to create. Defaults to 100. |
| [`-n`](#generation-limit) | The number of records to generate. Must not be used in combinaton with `-t`. |
| [`-t`](#generation-limit) | The length of time to create records for. Must not be used in combination with `-n`. |

### Prerequities

The data generator requires Python 3.

```bash
apt-get install python3
apt-get update
apt-get install -y python3-pip
```

Install dependencies using the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### Generator specification

The [generator specification](docs/genspec.md) is a JSON document that sets how the data generator will execute. When the `-f` option is used, the generation specification will be read from a file, otherwise the generator specification will be read from `stdin`.

A generator specification follows this structure:

```json
{
  "states": [ ... ],
  "emitters": [ ... ],
  "target": { },
  "interarrival": { }
}
```

The sections of the JSON document concern what each data generator worker will do.

* A list of [`states`](docs/genspec-states.md) that a worker can transition through.
* A list of [`emitters`](docs/genspec-emitters.md), listing the dimensions that will be output by a worker and what data they will contain.
* A [`target`](docs/tarspec.md) definition (optional), stating where records should be written. When not provided inside a generator specification, a separate JSON file can be specified using the `-o` argument. This allows for the same generator to be used with different targets.
* The `interarrival` time, controlling how often a new worker is spawned. The default maximum number of workers is 100, unless the `-m` argument is used.

### Target specification

Set the output of the data generator by setting the `target` object.

Use the _-o_ option to designate a target definition file name. The [target](docs/target.md) defines where the generated messages are sent.

### Record format

A text file with key names in braces (`{` and `}`) where emitter dimensions will be inserted.

This allows for formats other than JSON to be generated, such as CSV or TSV.

### Generation limit

Use either `-n` or `-t` to limit how long generation executes for. If neither option is present, the script will run indefinitely.

#### Limit generation to a length of time

Time durations may be specified in terms of seconds, minutes or hours.

For example, specify 30 seconds as follows:

```bash
python generator.py -f generator_spec.json -o target_spec.json -t 30S
```

Specify 10 minutes as follows:

```bash
python generator.py -f generator_spec.json -o target_spec.json -t 10M
```

Or, specify 1 hour as follows:

```bash
python generator.py -f generator_spec.json -o target_spec.json -t 1H
```

#### Limit generation to a number of records

Use `-n` to limit generation to a number of records.

```bash
python generator.py -f generator_spec.json -o target_spec.json -n 1000
```

### Simulated clock

Specify a start time in ISO format to instruct the driver to use simulated time instead of the system clock time (the default).

In the following example, the constraint is the number of records.

```bash
python3 generator.py -f conf/gen/example.json -o conf/tar/stdout.json -n 20 -s "2001-12-20T13:13"
```

* `example.json` generator specification is used.
* The `target` in `stdout.json` determines where the JSON records will be output.
* `-n` requires that only 20 rows are output.
* The synthetic `time` clock will start on 20th December 2001 at 13:13pm.

This results in:

```json
{"time":"2001-12-20T13:13:12.132","server":"127.0.0.5","client":"63.211.68.115","endpoint":"GET /api/users/73/contributions","response_time_ms":326}
{"time":"2001-12-20T13:13:17.464","server":"127.0.0.3","client":"79.58.216.203","endpoint":"GET /api/search?q=quantum-mechanics","response_time_ms":262}
{"time":"2001-12-20T13:13:20.776","server":"127.0.0.4","client":"96.54.85.35","endpoint":"GET /api/categories","response_time_ms":75}
{"time":"2001-12-20T13:13:28.023","server":"127.0.0.4","client":"96.54.85.35","endpoint":"GET /api/articles/56/contributors","response_time_ms":41}
{"time":"2001-12-20T13:13:28.077","server":"127.0.0.5","client":"18.202.244.47","endpoint":"POST /api/feedback","response_time_ms":179194}
```

In the next example, the constraint is duration. This will cause the generator to create as many JSON records as would fit into a given duration (see `-t` below).

```bash
python3 generator.py -f conf/gen/example.json -o conf/tar/stdout.json -t 1h -s "2027-03-12"
```

* The `-s` flag sets a synthetic clock start of 12th March 2027.
* Since `-t` is set to `1h`, the generator creates an hour's worth of data.

The result is a list of events spanning an hour from the time given in `-s`. This is therefore recommended when generating large volumes of data.

```json
{"time":"2027-03-12T00:00","server":"127.0.0.6","client":"60.138.23.232","endpoint":"GET /api/articles/102/history","response_time_ms":405}
{"time":"2027-03-12T00:00:06.157","server":"127.0.0.6","client":"73.198.96.12","endpoint":"GET /api/articles","response_time_ms":210}
{"time":"2027-03-12T00:00:06.623","server":"127.0.0.4","client":"87.21.26.43","endpoint":"GET /api/articles/42","response_time_ms":445}
:
:
{"time":"2027-03-12T00:59:59.961","server":"127.0.0.4","client":"87.21.26.43","endpoint":"GET /api/users/73/contributions","response_time_ms":489}
{"time":"2027-03-12T00:59:59.965","server":"127.0.0.4","client":"62.155.215.104","endpoint":"POST /api/users/login","response_time_ms":97521}
{"time":"2027-03-12T00:59:59.973","server":"127.0.0.5","client":"87.21.26.43","endpoint":"GET /api/articles/56/contributors","response_time_ms":118}
```
