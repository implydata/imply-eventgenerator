# TODO

## Break down the `202604-looping` branch

1. Tag `202604-looping` as `archive/202604-looping` and push the tag.
2. Start a subprocess branch from main with only the subprocess material. See
   [TODO-subprocess-branch.md](TODO-subprocess-branch.md).
3. Delete `202604-looping` locally and on origin.

## Engine

- Allow `"type": "variable"` in a state's `variables` block, so one variable can
  copy another's current value with its type kept. This enables chaining such as
  a referrer set to the previous request's URL in `zscaler_web`.
- Remove the deprecated `-m` alias for `-w` from `generator.py`, and switch
  `tools/generate_lake.py` to `-w`, both its own flag and the command it builds.
- Stop `--template` silently mis-rendering configs with more than one emitter.
  One template is applied to every emitter's records, and fields missing from a
  record render as blanks instead of raising an error.
- Make `percent_nulls` work or remove it. Every generator page documents it,
  but `create_record` never applies it, so no dimension type ever emits `null`.
- Low priority: add load-time definitions to configs, so a JSON fragment named
  once in a top-level `definitions` block can be reused with `{"$ref": "<name>"}`
  and substituted before parsing. This would remove repeats such as the public IP
  range written out three times in `ecommerce_furniture`.

## Docs

- Update `docs/datalake-export.md` for `-w`, the `bench_config_workers.py` and
  `bench_grid.py` tools, and the single-threaded engine.
- Replace `-m` with `-w` in the quick-start commands in
  `docs/presets/ecommerce_gifts.md` and `docs/presets/ecommerce_sports.md`.
- Remove the README link to `test.sh`, which doesn't exist.
- Add a Vale vocabulary for technical terms such as `config`, `datetime`,
  `enum`, `namespace`, and `interarrival`, so Vale's spell check stops flagging
  them in `docs/`.
- Document Jinja's built-in `tojson` filter in `docs/templates.md` for values
  that contain backslashes or quotes.

## Presets

- Check `palo_alto`, `zscaler_web`, and `vpc_flow_logs` for static values
  repeated across branches that could be set once in an earlier state.
- Add an `ocsf:network_activity` template for `palo_alto` traffic logs. Threat
  logs would need a security-finding OCSF class.
