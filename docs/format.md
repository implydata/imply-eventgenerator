# Output format reference

Use the `-f` option to specify a format file for output records. If not specified, JSON is used.

A format file is a text file with key names in braces (`{{` and `}}`) where emitter dimensions will be inserted.

This allows for formats other than JSON to be generated, such as CSV or TSV.

## Datetime formatting

When the key relates to a dimension containing a datetime-type, like `clock` or `timestamp`, you can apply an strftime pattern by using a `|` symbol. For example, the following will apply an "access_combined"-style date and time format to the `time` dimension:

```text
[{{time|%d/%b/%Y:%H:%M:%S %z}}]
```

This becomes:

```text
[23/Sep/2023:14:30:00 +0000]
```

## Environment variables

Format files support environment variable substitution using `%VARIABLE_NAME%` syntax. This is useful for injecting deployment-specific values (such as Splunk HEC metadata) into the output without modifying the format file itself.

For example:

```text
{"source":"%TARGET_SOURCE%","index":"%TARGET_INDEX%","event":"{{clientip}} {{authuser}}"}
```

Set the variables before running the generator:

```bash
TARGET_SOURCE="my/source" TARGET_INDEX="main" python generator.py -c conf/gen/example.json -f conf/form/my_format.txt -n 10
```

The generator will exit with an error if any environment variables referenced in the format file are not set.
