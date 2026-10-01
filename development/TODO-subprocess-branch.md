# Subprocess branch

After the main-side PRs land, restart the subprocess work on a fresh branch from
main, not by merging main into `202604-looping`. A trial merge on 2026-09-30
showed three problems:

- The engine conflicts can only be resolved by writing the subprocess port
  inside the merge commit.
- Some founding-commit content is silently lost, because git applies main's
  reverts of those commits.
- Presets end up split across two type-name schemes.

Keep all parent-child work on this branch. Nothing on main should depend on it.

## Carry over from `archive/202604-looping`

- `presets/configs/ecommerce/diy/`: the DIY preset, which is the main subprocess
  test case. See [DIY preset](#diy-preset).
- `presets/configs/test_loop_parent.json` and `test_loop_child.json`. The parent
  config fails validation at the branch tip because it's missing the `config`
  field.
- `docs/states/event-start-message.md` and
  `docs/states/subprocess-multi-variables.md`.
- `docs/language.md`, the language feature inventory, and the README paragraph
  that introduced it: "A config is source code. The engine is a runtime. The
  language has first-class primitives for randomness, time, and concurrency —
  things no general-purpose language treats as primitive because they are
  incidental to most programs but central to this one." Both were removed from
  main when the founding loop commits were reverted.
- `variable:template`: the `DimensionVariableTemplate` class in
  `ieg/dimensions.py`, its hook in `create_record`, and
  `docs/dimensions/variable/template.md`. It's how child configs build values
  from variables their parent passes in.

## Design as built on the branch

Two state types call a child config:

- `subprocess` runs the child config once.
- `subprocess:multi:variables` is a for-each loop, modelled on the BPMN
  sequential multi-instance subprocess. It runs the child once per entry in
  `items`.

```json
{
  "name": "load_components",
  "type": "subprocess:multi:variables",
  "config": "presets/configs/child.json",
  "items": [
    [
      { "name": "url", "type": "static", "value": "/index.html" },
      { "name": "bytes", "type": "static", "value": 1247 }
    ],
    [
      { "name": "url", "type": "static", "value": "/static/style.css" },
      { "name": "bytes", "type": "static", "value": 8432 }
    ]
  ],
  "next": "done"
}
```

- Each entry in `items` is a list of variable specs, in the same format as an
  activity's `variables` block. Before each child run, the engine evaluates that
  entry's specs into the worker's variables, using the normal variable path.
- A child config's entry point is `event:start:message`, modelled on the BPMN
  message start event. It has no `cardinality_distribution`, because the parent
  triggers it, and it can have a `variables` block for standalone defaults. A
  child with no `event:start:timer` correctly fails standalone validation, and
  the engine raises a clear error if a called config has no
  `event:start:message`.
- Child configs inherit the parent's emitters and can add their own.
- `variable_defaults`, a top-level block that pre-set variables before the state
  machine started, was removed along the way. Defaults belong to the parent's
  `items` or to a `variables` block on `event:start:message`.
- An earlier idea, a top-level `constants` block, was dropped because `items`
  covered parameter passing. Load-time definitions for repeated literal
  values, which a variables-based block couldn't provide, are now a separate
  item in [TODO.md](TODO.md).

## Design problems to solve before porting the engine code

- Child config paths are resolved from the current working directory, not from
  the parent config's location.
- `validate.py` never opens child config files, so errors in them only show up
  at run time.
- Children write straight into the parent's variables, with no separate scope.
- `items` in `subprocess:multi:variables` is a hand-written list. DIY spells out
  77 entries in full.
- The session-length estimate and the benchmark tools don't know about child
  state machines.
- Output from `test_loop_parent` wasn't reproducible with `--seed` and `-s` on
  the branch, so a byte-diff couldn't verify it. Find the cause as part of the
  port.
- The branch's subprocess code is thread-based. It has to be rewritten as simpy
  generators on top of the `StateBase` subclasses in `ieg/states.py`. Start by
  extracting two pieces from `DataDriver`, as the branch had them
  (`run_state_machine` and `_parse_states`): a generator that runs a states
  dict from a given entry state against a given variables dict, and a
  function that parses a list of state dicts with a given set of emitters.
  Today both are inline in `DataDriver.__init__` and `session_process`.
- `fmt_config.py` sorts every `variables` block by type and then by name. Once a
  template can read another variable in the same block, that reordering can
  break evaluation order. Either stop sorting `variables` blocks, or have
  `validate.py` flag a template that reads a variable defined later in the
  block.

## Volume effects

In an April experiment, adding three asset loads per browse event to
`ecommerce.json` raised PT6H output (seed 42) from about 265,000 to 615,000
rows, about 2.3 times, while the `-w` ceiling stayed at about 2,112. Little's
Law explains this: the asset loads add 0.03 to 0.45 seconds to each session,
which is negligible against 90 to 300 seconds of browse pauses, so concurrency
barely changes while rows per browse event go from one to four.

When a subprocess adds iterations, estimate the session duration before and
after. If the added delay is small next to the dominant pauses, the ceiling is
unaffected and volume grows in proportion to the extra rows.

## DIY preset

A hardware-store ecommerce preset, separate from the `ecommerce*.json` presets
on main. It lives in `presets/configs/ecommerce/diy/`:

- `ecommerce_diy.json`: the entry point.
- `categories/`: one config per category (`power_tools`, `hand_tools`,
  `plumbing`, `electrical`, `paint`, `lumber`, `garden`).
- `shared/`: reusable child configs.

### Routing

`session_start` → `route_actor` sends 99.7% of sessions to the human path, 0.1%
to the hacker, and 0.2% to the bot. The hacker and bot are child configs that
never reach `setup_session`, so they set every variable the emitter needs
themselves.

The human path is `setup_session` (emits `/`) → `load_statics` →
`preload_assets` → `route_browse` → a category child config → `route_continue`,
then optionally `pause_checkout` → `emit_checkout` → `route_checkout` →
`pause_thank_you` → `emit_thank_you` → `session_end`.

- `route_continue`: 45% browse again, 30% checkout, 25% end.
- `route_checkout`: 65% complete to the thank-you page, 35% abandon back to
  browsing.

Each category config runs `init` → `emit_browse` → `pause_browse` →
`route_after_cat` → `emit_view_product` → `load_product_assets` →
`pause_view_product` → `route_after_product` → optionally `add_to_cart` →
`done`. `route_after_product` is 25% view another product, 15% back to browse,
45% add to cart, 15% exit. Browse pauses are 20–60 seconds for power tools,
25–75 seconds for plumbing and electrical, and 15–45 seconds for the rest.

### Asset loading

An early version loaded 11 thumbnails and 3 static files on every category page,
which made 82% of a day's rows asset requests. The fix moved thumbnails to a
one-off preload at session start:

| Config                                        | Loads                                                                            | When                   | `bytes_out` |
| --------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------- | ----------- |
| `load_statics.json` → `load_static_file.json` | `/static/app.js`, `/static/vendor.js`, `/static/main.css`                        | Once per session       | 30–500 KB   |
| `preload_assets.json` → `load_cat_image.json` | 77 thumbnails, `/images/{category}/{slug}-thumb.jpg`                             | Once per session       | 4–35 KB     |
| `load_product_assets.json`                    | `-hero.jpg` (120–600 KB), `-gallery-1.jpg` and `-gallery-2.jpg` (80–350 KB each) | Each product page view | Varies      |

Even so, in a PT1H run on 2026-09-23 about 88% of rows were `/images` preload
hits, roughly 84 per session.

Every emitting activity sets `var_bytes_out`, and the emitter reads it: homepage
5–80 KB, category 8–60 KB, product 10–80 KB, checkout 5–30 KB, thank-you 3–20
KB, cart API 200 B–2 KB, bot page crawl 5–80 KB, hacker error responses 200 B–5
KB.

Other shared configs: `add_to_cart.json` (5–15 second pause, then
`/cart/add/{category}/{product}`), `hacker.json` (a rapid probe loop, mean 0.01
seconds, 40 suspicious paths, error status codes), and `bot.json` (a crawl loop,
mean 1 second, covering `robots.txt`, the sitemap, and category and product
URLs).

### Still to do

- Benchmark the `-w` ceiling and write `docs/presets/ecommerce_diy.md`.
- Add a `tools/generate_all.json` profile.
- Optional realism improvements: update the referrer within a session, return
  304 Not Modified for assets on repeat sessions from the same client, and use
  POST for cart adds.
