# DONE

- Replaced the single `State` class with one class per state type, each with
  its own parsing, validation, and behaviour, and gave each state type its own
  page under `docs/states/`. Seeded output is unchanged. Sustained generation is
  about 5% faster, and peak memory under heavy concurrency is 25% lower. Added
  `tools/bench_engine/` for measuring engine speed and memory.
- Replaced dimension type names with three kinds (`static`, `variable`, and
  `generator:<class>`), with validation errors naming the replacement for each
  retired name. Moved the dimension docs into `docs/dimensions/`, and removed
  redundant static-value sets in `pbx_calls`, `endpoint_network`, `ssh_auth`,
  and the five ecommerce presets.
