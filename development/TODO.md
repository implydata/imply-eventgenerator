# TODO

## Engine

- Allow `"type": "variable"` in a state's `variables` block, so one variable can
  copy another's current value with its type kept. This enables chaining such as
  a referrer set to the previous page in `zscaler_web` and the ecommerce
  presets. A copy alone carries a path such as `/products`, not the full URL a
  real referrer has, so realistic referrers also need a way to join values.
- Remove the deprecated `-m` alias for `-w` from `generator.py`, and switch
  `tools/generate_lake.py` to `-w`, both its own flag and the command it builds.
- Fix `--template` applying one template to every emitter's records:
  [#43](https://github.com/implydata/imply-eventgenerator/issues/43).
- Make `percent_nulls` work or remove it:
  [#42](https://github.com/implydata/imply-eventgenerator/issues/42).

## Docs

- Update `docs/datalake-export.md` for `-w`, the `bench_config_workers.py` and
  `bench_grid.py` tools, and the single-threaded engine. Its caveat that seeded
  ecommerce runs aren't reproducible no longer holds.
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

## Ideas

- Consider letting one config call another as a step, optionally once per item
  in a list. See [TODO-subprocesses.md](TODO-subprocesses.md) for the brief and
  the history of the first attempt.
- Consider load-time definitions, so a JSON fragment named once in a top-level
  `definitions` block can be reused with `{"$ref": "<name>"}` and substituted
  before parsing. This would remove repeats such as the public IP range written
  out three times in `ecommerce_furniture`.
