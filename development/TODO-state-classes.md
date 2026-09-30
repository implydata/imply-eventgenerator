# State classes and per-state docs (PR 2)

Replace the single `State` class in `ieg/states.py` with one class per state
type, and document each type on its own page.

## Code

- Write the classes fresh for the simpy engine. The branch's
  `StateBase.execute()` blocks on `sleep()`, so use it only as a sketch of the
  shape. On main, a state's step must be a generator that uses `yield from` for
  timer states.
- Give each class its own `parse()` class method and `validate()`, the same way
  the dimension classes already work, so `ieg/core.py` no longer needs a
  per-type `if` chain to build states.
- Keep only timer states holding a delay. Today every `State` carries one, with
  a constant zero for most types.
- Keep main's cumulative-weights `random.choices` call in the gateway, so random
  numbers are drawn in the same order as before.
- Adapt or remove `estimate_session_length`, which walks `state.transitions` and
  `state.delay`. Check whether any tool calls it first.
- Cover only the five state types on main. Subprocess and `event:start:message`
  stay out.

## Docs

- Make `docs/states.md` an index page.
- Add `docs/states/event-start-timer.md`, `event-intermediate-timer.md`,
  `activity.md`, `gateway-exclusive.md`, and `event-end.md`, starting from the
  branch's pages. Re-apply main's edits: `-w`, the `-i` interval override
  paragraph, and removal of "worker thread" wording.
- Keep content that spans types, such as the variable lifecycle section in
  today's `states.md`, in `states.md`, `docs/patterns.md`, or
  `docs/best-practices.md`, not in the per-type pages.
- Update the docs table in `CLAUDE.md` to point at `docs/states/<type>.md`, with
  the rule that a new state type gets its own page and a row in the `states.md`
  index.

## Verification

Run a seeded byte-diff of every preset before and after. It should be identical.

- Command:
  `python generator.py -c presets/configs/<name>.json -r PT6H -s "2024-01-01T00:00:00" --seed 42 2>/dev/null | md5`.
  The simpy engine is deterministic at the default `-w`, and PT6H exercises
  every Actor type, including rare paths like the ecommerce bot and hacker.
- If only the key order differs, compare the parsed records as well. The
  formatter's dimension sort can change the output key order without changing
  any value.
