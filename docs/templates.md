# Output templates

Templates are named output formats embedded directly in a generator config. They let a single config produce many different output shapes — JSON, CSV, NCSA combined logs, key-value pairs — without needing separate format files.

## Using a template

Select a template by name at the command line with `--template`:

```bash
python generator.py -c presets/configs/ecommerce.json --template access_combined -n 20 -s "2025-01-01T00:00"
```

`--template` and `-f` are mutually exclusive. If the config has a `templates` block, use `--template`; if you have a standalone format file, use `-f`.

## The `templates` block

Templates live in a top-level `templates` object in the generator config, keyed by template name:

```json
{
  "templates": {
    "my_template": {
      "body": "{{ time.timestamp()|int }} {{ client }} {{ status }}"
    },
    "csv": {
      "header": "time,client,status",
      "body": "{{ time.timestamp()|int }},{{ client }},{{ status }}"
    }
  },
  "states": [ ... ],
  "emitters": [ ... ]
}
```

Each template has:

| Field | Description | Required? |
| --- | --- | --- |
| `body` | The Jinja2 template string rendered once per record. | Yes |
| `header` | A line written once before any records (useful for CSV column headers). | No |

## Template syntax

Templates are rendered using [Jinja2](https://jinja.palletsprojects.com/), a Python templating engine. Each `body` (and `header`) string is a Jinja2 template: expressions in `{{ }}` are replaced with field values, and control structures like `{% if %}` are supported. Every emitter dimension is available by name as a template variable.

### Field values

```text
{{ client }}           → 66.249.65.12
{{ status }}           → 200
{{ bytes_out }}        → 4823
```

### Datetime formatting

Datetime fields (e.g. `time`) are Python `datetime` objects, so Jinja2's standard methods apply:

```text
{{ time.strftime('%d/%b/%Y:%H:%M:%S') }}   → 01/Jan/2025:00:00:03
{{ time.timestamp()|int }}                 → 1735689603
```

### Conditional output

```text
"{{ uri_path }}{% if uri_query %}?{{ uri_query }}{% endif %}"
```

This renders `?query=string` only when `uri_query` is non-empty.

### Environment variables

Use `env.VARIABLE_NAME` to substitute environment variables at render time:

```text
{"index": "{{ env.SPLUNK_INDEX }}", "event": "{{ client }} {{ status }}"}
```

`env.get('VAR', 'default')` is available for optional variables. Any `env.VARIABLE_NAME` reference (without `.get`) causes `--validate` to fail if the variable is not set — the same fail-loud behaviour as the legacy `-f` path.

## Validation

Run `--validate` to check the config and any referenced template before generating data:

```bash
python generator.py -c presets/configs/ecommerce.json --template apache:access:json --validate
```

This checks that the named template exists and that all referenced environment variables are set.
