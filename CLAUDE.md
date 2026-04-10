# Claude Code guidance — imply-eventgenerator

## Actor-first design

Every config must have an agreed **Actor** before any JSON is written. An Actor is the entity that flows through the state machine — one worker thread, one journey. Propose the Actor(s) and their high-level workflow and wait for confirmation before writing any config.

- A config can have multiple Actor *types* (e.g. Human, Hacker, Bot in the ecommerce preset), routed at session start via a routing state such as `global_init`.
- All Actor types share the same `-m` worker pool, capped by Little's Law.
- `-m` caps the number of simultaneously active sessions. When set below the natural concurrency (L = λW), it reduces throughput — in both real-time and simulated modes. When at or above L, it has no effect on throughput; the interarrival `mean` is the binding constraint.
- In simulated mode, the Clock serialises threads for **time-ordering** (advancing simulated time in scheduled-event order). This is separate from the concurrency cap: the spawning thread still enforces `effective_max` and sleeps 5 simulated seconds when at capacity. Do not conflate time-ordering serialisation with bypassing the concurrency constraint.

## Preset structure

Each preset consists of:

| Artifact | Location | Required? |
| --- | --- | --- |
| Config JSON | `presets/configs/<name>.json` | Yes |
| Preset doc | `docs/presets/<name>.md` | Yes |
| Schedule JSON | `presets/schedules/<name>.json` | No — only when time-based patterns (e.g. business hours) are needed |

The `conf/` directory and `docs/conf/` are deprecated — ignore them entirely.

The ecommerce configs (`ecommerce.json`, `ecommerce_furniture.json`, `ecommerce_lighting.json`) are fully independent — editing one does not imply checking the others.

## Preset doc structure

Every `docs/presets/<name>.md` must follow this structure:

1. Title + one-paragraph description
2. **Quick start** — copy-paste commands covering common output formats
3. **Templates** — table of available `--template` values and their output
4. **Output fields** — table of emitted fields and descriptions
5. [Preset-specific sections] — e.g. product categories, session routing, per-Actor flow diagrams
6. **Concurrency (`-m`)** — Little's Law table (W, mean, λ, max useful `-m`). Always required — users need to know there is an upper limit on volume.

## Keeping docs and code in sync

The reference docs in `docs/` are the authoritative source for what the engine supports. These must stay in sync with the code:

| Doc | Covers |
| --- | --- |
| `states.md` | State type field reference |
| `emitters.md` | Emitter structure and dimension fields |
| `distributions.md` | Distribution types and parameters |
| `field-generators.md` | Index of all field generator types |
| `docs/types/<type>.md` | Per-type detail — one file per field generator type |
| `templates.md` | Template syntax and the `templates` block |
| `schedules.md` | Schedule format and multiplier semantics |

- If a code change adds or modifies a state type, distribution type, emitter option, or field type, update the relevant doc in the same pass — not as a follow-up.
- `field-generators.md` is an index page; the per-type detail lives in `docs/types/`. When a new field type is added, create `docs/types/<type>.md` **and** add a row to `field-generators.md`.
- If asked to write a config that uses a distribution or field type not present in `docs/`, **stop and flag it** rather than writing JSON and hoping it works.

## Testing configs

**Always use the synthetic clock.** Never run a test without `-s` — real-time mode means waiting as long as the simulated period, which can be an hour or more.

```bash
# Minimal smoke test
python generator.py -c presets/configs/<name>.json -n 100 -s "2024-01-01T00:00:00" | head -20

# Full validation — use at least one simulated hour to surface config errors
python generator.py -c presets/configs/<name>.json -r PT1H -s "2024-01-01T00:00:00" > /tmp/test.json
```

Config errors (bad field references, wrong distributions, missing variables) often only surface after a reasonable volume of data — run the PT1H test before declaring a preset done.

## Config JSON authoring

Before writing any JSON, read `docs/how-to-build-a-config.md` — it walks through the full design process from Actor definition to tested config (Steps 1–10). The reference docs listed above are authoritative on what the engine supports; flag any discrepancy rather than guessing.

## Config JSON style

After writing or editing any config, run the formatter to enforce consistent field ordering and compact/expanded forms:

```bash
python tools/fmt_config.py presets/configs/<name>.json
```

The formatter is the authoritative source of style rules. Run `--check` in CI to detect unformatted files. The formatter guarantees no data loss: it compares the parsed original and output structurally before writing, and aborts if they differ.
