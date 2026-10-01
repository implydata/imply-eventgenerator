# Claude Code guidance — imply-eventgenerator

## Actor-first design

Every config must have an agreed **Actor** before any JSON is written. An Actor is the entity that flows through the state machine — one session, one journey. Propose the Actor(s) and their high-level workflow and wait for confirmation before writing any config.

- A config can have multiple Actor *types* (e.g. Human, Hacker, Bot in the ecommerce preset), routed at session start via a routing state such as `global_init`.
- All Actor types share the same `-w` worker pool, capped by Little's Law.
- `-w` caps the number of simultaneously active sessions. When set below the natural concurrency (L = λW), it reduces throughput — in both real-time and simulated modes. When at or above L, it has no effect on throughput; the interarrival `mean` is the binding constraint.
- The engine is a single-threaded `simpy` event loop. At each arrival, `arrival_process` starts a new session only if fewer than `effective_max` sessions are active. Otherwise the arrival is dropped: there's no queue and no retry.

## Preset structure

Each preset consists of:

| Artifact | Location | Required? |
| --- | --- | --- |
| Config JSON | `presets/configs/<name>.json` | Yes |
| Preset doc | `docs/presets/<name>.md` | Yes |
| Schedule JSON | `presets/schedules/<name>.json` | No — only when time-based patterns (e.g. business hours) are needed |

The `conf/` directory and `docs/conf/` are deprecated — ignore them entirely.

The ecommerce configs (`ecommerce.json`, `ecommerce_furniture.json`, `ecommerce_gifts.json`, `ecommerce_lighting.json`, `ecommerce_sports.json`) are fully independent — editing one does not imply checking the others.

## Preset doc structure

Every `docs/presets/<name>.md` must follow this structure:

1. Title + one-paragraph description
2. **Quick start** — copy-paste commands covering common output formats
3. **Templates** — table of available `--template` values and their output
4. **Output fields** — table of emitted fields and descriptions
5. [Preset-specific sections] — e.g. product categories, session routing, per-Actor flow diagrams
6. **Volume** — always required, in this exact order:
   1. State the empirical worker ceiling using this standard preamble verbatim (it's `tools/bench_config_workers.py`'s own first line — paste it, don't paraphrase it), substituting only the numbers: "The default start interval for workers in this preset is I seconds, with each worker busy for S seconds on average. The maximum number of workers that can be busy at the same time is therefore S/I = N; increasing available workers (using `-w`) without adjusting how often they begin work (using `-i`) has no effect." Grounded in Little's Law (L = λW) run in reverse: the empirically-found ceiling (L=N) and the known start interval (1/λ=I) together imply the average busy-time per worker (W=S), shown as an explicit division so the reader sees *why* N is the cap, not just that it is — no separate measurement needed. Optionally follow with "At this preset's low volume, treat this as approximate rather than exact." for a single-digit ceiling (omit entirely otherwise — don't rephrase it into a false caveat). Measured with `tools/bench_config_workers.py -c presets/configs/<name>.json` at the preset's own default `event:start:timer` interval (see Step 10 of `docs/how-to-build-a-config.md`).
   2. The chart from that same `bench_config_workers.py` run (its default markdown output is chart-only, no table — paste the `xychart-beta` block as-is, no separate rows/wall-clock table).
   3. An actionable lead sentence bridging into the grid: "Adjust `-i` and `-w` to model a busier/faster `<preset>`." (or the preset-appropriate verb), then the illustrative 2D grid from `tools/bench_grid.py -c presets/configs/<name>.json` (its default `-w`/`-i` grid, which already includes the preset's own interval as a `(default)`-marked row) — paste its markdown table as-is.
   Keep the prose to plain, direct statements of fact about the preset (ceiling, how it scales, what lever controls volume) — do not narrate the measurement methodology, the benchmarking tools' internals, or the grid's own symbol legend beyond pasting it; those belong in the tools' docstrings or this file, not a preset doc.

## Keeping docs and code in sync

The reference docs in `docs/` are the authoritative source for what the engine supports. These must stay in sync with the code:

| Doc | Covers |
| --- | --- |
| `states.md` | Index of state types, and behaviour shared across them |
| `states/<type>.md` | Per-type detail — one file per state type |
| `emitters.md` | Emitter structure and dimension fields |
| `distributions.md` | Distribution types and parameters |
| `dimensions/static.md` | The `static` dimension type |
| `dimensions/variable.md` | The `variable` dimension type |
| `dimensions/generator.md` | Index of all `generator:*` types |
| `dimensions/generator/<type>.md` | Per-type detail — one file per generator type |
| `templates.md` | Template syntax and the `templates` block |
| `schedules.md` | Schedule format and multiplier semantics |

- If a code change adds or modifies a state type, distribution type, emitter option, or dimension type, update the relevant doc in the same pass — not as a follow-up.
- `states.md` is an index page; the per-type detail lives in `states/`. When a new state type is added, create `states/<type>.md` **and** add a row to the `states.md` table.
- `dimensions/generator.md` is an index page; the per-type detail lives in `dimensions/generator/`. When a new generator type is added, create `dimensions/generator/<type>.md` **and** add a row to `dimensions/generator.md`.
- If asked to write a config that uses a distribution or dimension type not present in `docs/`, **stop and flag it** rather than writing JSON and hoping it works.
- If a change alters a preset's output volume or session timing, re-profile it and update its entries in `tools/generate_all.json` and its doc's **Volume** section. A seeded byte-diff (`--seed` with `-s`) of the preset's output before and after the change shows whether re-profiling is needed.

## Testing configs

**Always use the synthetic clock.** Never run a test without `-s` — real-time mode means waiting as long as the simulated period, which can be an hour or more.

```bash
# Minimal smoke test
python generator.py -c presets/configs/<name>.json -n 100 -s "2024-01-01T00:00:00" | head -20

# Full validation — use at least one simulated hour to surface config errors
python generator.py -c presets/configs/<name>.json -r PT1H -s "2024-01-01T00:00:00" > /tmp/test.json
```

Config errors (bad field references, wrong distributions, missing variables) often only surface after a reasonable volume of data — run the PT1H test before declaring a preset done.

### Testing `ocsf:*` templates

Any template emitting OCSF output must be validated against the real OCSF JSON Schema, not just eyeballed — the JSON can look plausible while still violating the schema (wrong field type, invalid enum value, missing required nested field). Use `tools/ocsf/validate.py` rather than writing an ad hoc check:

```bash
python tools/ocsf/validate.py -c presets/configs/<name>.json --template ocsf:<class_name>
```

See `tools/ocsf/README.md` for the field-mapping conventions (`activity_id`/`severity_id` derivation, etc.) used across existing `ocsf:*` templates, and two Jinja/jsonschema pitfalls worth knowing before writing a new one.

### Verifying engine changes

Before changing anything in `ieg/`, decide whether the change alters *when* events happen or which random numbers are drawn. If it doesn't, it's a refactor:

- Save seeded output of every preset before and after, and diff it: `python generator.py -c presets/configs/<name>.json -r PT6H -s "2024-01-01T00:00:00" --seed 42 | md5`. The engine is deterministic at the default `-w`, and PT6H reaches rare paths such as the ecommerce bot and hacker. Output must be byte-identical. If only the key order differs, compare the parsed records too: the formatter's dimension sort can reorder keys without changing values.
- Measure speed and memory with `tools/bench_engine/bench_engine.py`: save `--out` before the change and `--compare` after it. See `tools/bench_engine/README.md`.

If the change does alter timing or random draws, a byte-diff can't prove it safe. Compare output distributions across several seeds instead, and re-check `tools/generate_all.json` tiers near their caps.

## Config JSON authoring

Before writing any JSON, read `docs/how-to-build-a-config.md` — it walks through the full design process from Actor definition to tested config (Steps 1–10). The reference docs listed above are authoritative on what the engine supports; flag any discrepancy rather than guessing.

## Config JSON style

After writing or editing any config, run the formatter to enforce consistent field ordering and compact/expanded forms:

```bash
python tools/fmt_config.py presets/configs/<name>.json
```

The formatter is the authoritative source of style rules. Run `--check` in CI to detect unformatted files. The formatter guarantees no data loss: it compares the parsed original and output structurally before writing, and aborts if they differ.
