# Claude Code guidance — imply-eventgenerator

## Actor-first design

Every config must have an agreed **Actor** before any JSON is written. An Actor is the entity that flows through the state machine — one worker thread, one journey. Propose the Actor(s) and their high-level workflow and wait for confirmation before writing any config.

- A config can have multiple Actor *types* (e.g. Human, Hacker, Bot in the ecommerce preset), routed at session start via a routing state such as `global_init`.
- All Actor types share the same `-m` worker pool, capped by Little's Law.
- `-m` is a concurrency *cap*, not a volume knob. Volume is controlled by interarrival `mean`.

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

The section structure in `docs/best-practices.md` under "README Files" is outdated — ignore it.

## Keeping docs and code in sync

The reference docs in `docs/` (especially `emitters.md`, `distributions.md`, `field-generators.md`) define what the engine actually supports. These must stay in sync with the code.

- If a code change adds or modifies a distribution type, emitter option, or field type, update the relevant doc in the same pass — not as a follow-up.
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

Config files grow large quickly. Keep the code and `docs/` reference docs in sync at all times — if a field or distribution type isn't documented, clarify before using it.
