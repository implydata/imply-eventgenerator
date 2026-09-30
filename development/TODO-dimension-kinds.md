# Dimension kinds (PR 1)

Replace the dimension type names with three explicit kinds, as a clean swap with
no aliases:

| Kind            | Syntax                                  | Replaces                                                                                         |
| --------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Fixed value     | `"type": "static", "value": ...`        | `string:static`, `int:static`                                                                    |
| Variable lookup | `"type": "variable", "variable": "..."` | Unchanged                                                                                        |
| Sampled value   | `"type": "generator:<class>"`           | `int`, `float`, `enum`, `string`, `ipaddress`, `counter`, `timestamp`, `clock`, `object`, `list` |

Today `type` does double duty: some values name a kind (`variable`,
`string:static`) and others name a generator implementation (`int`, `enum`).
After this change, the part before the colon always names the kind. The
`distribution` object stays nested, as it is today.

## Source material on `202604-looping`

Main has barely changed these files since the branch was cut, so check out the
branch's version and re-apply main's small edits:

- `ieg/dimensions.py`: re-apply main's two performance changes (the precomputed
  `_chars_list` and the `tz=` argument to `datetime.fromtimestamp`). Leave out
  `DimensionVariableTemplate`, which moves to the subprocess branch.
- `docs/dimensions/` tree and `docs/emitters.md`: re-apply main's `-m` to `-w`
  edits from `docs/types/`. The branch's pages also fix the broken relative
  links in `docs/types/` (for example `./field-generators.md` and
  `./distributions.md`).
- `presets/configs/pbx_calls.json`: take the branch's version as-is. It already
  includes the hoisting.
- `presets/configs/endpoint_network.json`, `ssh_auth.json`, `ecommerce.json`,
  `ecommerce_furniture.json`, `ecommerce_lighting.json`: re-add the OCSF
  template blocks that main added since, or run the migration script on main's
  versions.
- `tools/fmt_config.py`: take the branch's type ordering, without the subprocess
  state entries. Keep `generator:clock` first in emitter dimensions, so the
  record timestamp stays the first output key.

## New work

- Restore `percent_nulls` on `static`. The branch dropped it.
- In `ieg/validate.py`, reject each retired type name with a message naming its
  replacement, for example `'int' was renamed to 'generator:int'`.
- Write a migration script, and run it on `vpc_flow_logs`, `ecommerce_gifts`,
  `ecommerce_sports`, `palo_alto`, and `zscaler_web`.
- Redo the rename edits in `docs/patterns.md`, `docs/best-practices.md`, and
  `docs/how-to-build-a-config.md` against main's current text.
- Update the docs table in `CLAUDE.md` for the `docs/dimensions/` tree.
- Hoist `var_transport` into `setup_connection` in `endpoint_network`.
- Remove redundant re-sets of values that an earlier state already set:
  `var_line_type` in `emit_session_closed` in `ssh_auth`, and `var_user` in
  `emit_bot` in all five ecommerce presets.
- After the move, check that no doc links point at `field-generators.md` or
  `docs/types/`.

## Verification

Run a seeded byte-diff of every preset before and after. It should be identical.

- Command:
  `python generator.py -c presets/configs/<name>.json -r PT1H -w 1 -s "2024-01-01T00:00:00" --seed 42 2>/dev/null | md5`.
  The ecommerce presets need `-w 1` to be reproducible.
- Run the old and new versions of each preset as separate commands, not in one
  loop. On the branch, running them one after another in a loop produced
  occasional false mismatches.
- If the formatter reorders emitter dimensions, the output's key order changes
  and so does the hash, even though no value changes. Check key order before
  treating a mismatch as a real difference.
- If any preset really differs, find out why before merging, and re-profile it
  in `tools/generate_all.json`.
