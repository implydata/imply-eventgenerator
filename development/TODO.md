# TODO

## Let a schedule mimic a timezone offset

`gmm_temporal` schedules (`ieg/distributions.py`'s `DistGMMTemporal` and
`Schedule`) key their day/hour profiles on `utc_hour`, and always resolve
the current hour against true UTC (see `fd9e65f`, which made real-time
mode's clock genuinely UTC-aware — schedule modulation inherited that
fix for free, since it reads the clock's own hour with no conversion of
its own).

That's the right default, but it's not the only thing anyone deploying
this would want: the same config should be able to drive a
region-appropriate "business hours" pattern on differently-located
deployments (e.g. a demo server in each of US East, UK, and China) without
hand-duplicating an near-identical schedule file per region just to shift
every `utc_hour` value.

Proposed: let a schedule (or a CLI override, mirroring how `-i` overrides
a config's own interarrival mean) state the timezone its `utc_hour` values
should be interpreted against — e.g. a fixed offset ("UTC+9") or an
explicit IANA zone name, so `Asia/Shanghai`'s business hours show up as
business hours on that deployment, `Europe/London`'s on that one, from the
same schedule JSON.

Open design question, not yet decided: should this support only an
explicit zone/offset (simplest, most robust — stdlib `zoneinfo` handles
DST correctly forever, no new dependency), an auto-detected "local" mode
that reads the host's own system timezone (more convenient per-deployment,
but a naive `datetime.now().astimezone()` shortcut only captures a fixed
UTC offset that can silently go stale across a DST transition on a
long-running `Restart=always` systemd service — doing this properly would
need a dependency like `tzlocal`), or both.

Also worth doing as part of this: `DistGMMTemporal.get_sample()` and
`Schedule.get_multiplier()` currently duplicate the exact same
`now.isoweekday()` / `now.hour + now.minute/60 + now.second/3600`
extraction logic — whichever timezone-resolution approach is chosen needs
to be applied in both places, which is a good opportunity to consolidate
them into one shared method instead of fixing the same thing twice.

Must stay backward compatible: no existing preset schedule specifies a
timezone today, and all of them must keep meaning true UTC exactly as they
do now when the field is omitted.
