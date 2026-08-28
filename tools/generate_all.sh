#!/usr/bin/env bash
#
# Run generator.py + tools/split_stream.sh in series for every (profile, template)
# pair in tools/generate_all.json, one continuous run per pair. --start/--duration
# pass straight through to generator.py's own -s/-r with no transformation, so this
# stays a thin wrapper rather than a second date-range convention to learn.
#
# Every profile's config file, schedule, template list, and per-volume -i/-w settings
# live in tools/generate_all.json, not discovered from presets/configs/*.json at
# runtime — a volume's -i/-w needs a human to have actually benchmarked it first (see
# docs/how-to-build-a-config.md), so a newly-added preset shouldn't silently appear in
# a bulk export with guessed settings. Adding a new preset means adding an entry there
# — see the "Register it for bulk export" step in docs/how-to-build-a-config.md.
set -euo pipefail

# Re-exec under caffeinate (macOS) so idle sleep can't interrupt what's often a
# multi-hour run — a real, observed cause of hangs the engine has no recovery
# from (see docs/generate-all.md#sleep-protection). Guarded by an env var so
# this only wraps once, not on every re-exec.
if [[ -z "${GENERATE_ALL_CAFFEINATED:-}" ]]; then
  export GENERATE_ALL_CAFFEINATED=1
  if command -v caffeinate >/dev/null 2>&1; then
    echo "info: running under caffeinate -i, so idle sleep won't interrupt this run — a sleep/wake cycle mid-run has caused real, unrecoverable hangs before. This only covers idle sleep: closing the lid still sleeps the machine regardless, so leave it open (or plugged in with lid open) for the duration." >&2
    exec caffeinate -i "$0" "$@"
  else
    echo "warning: caffeinate not found — this run has no protection against idle sleep interrupting it mid-way, which has caused real hangs on long runs. caffeinate ships with macOS by default; on other platforms, make sure your own power/sleep settings won't interrupt a multi-hour run." >&2
  fi
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$REPO_ROOT/presets/configs"
SCHEDULE_DIR="$REPO_ROOT/presets/schedules"
GENERATE_ALL_CONFIG="$REPO_ROOT/tools/generate_all.json"

# Prints one profile name per line, in tools/generate_all.json's own order.
profile_names() {
  python3 -c "
import json
data = json.load(open('$GENERATE_ALL_CONFIG'))
for name in data.get('profiles', {}):
    print(name)
"
}

# Prints "<config file> <schedule file or ->" for one profile.
profile_settings() {
  python3 -c "
import json, sys
data = json.load(open('$GENERATE_ALL_CONFIG'))
p = data.get('profiles', {}).get('$1')
if p is None:
    sys.exit(1)
print(p['config'], p.get('schedule') or '-')
"
}

# Prints "<template>=<extension>" lines for one profile.
templates_for() {
  python3 -c "
import json, sys
data = json.load(open('$GENERATE_ALL_CONFIG'))
p = data.get('profiles', {}).get('$1')
if p is None:
    print(\"error: no such profile '$1'\", file=sys.stderr)
    sys.exit(1)
for t in p.get('templates', []):
    print(f\"{t['name']}={t['ext']}\")
"
}

usage() {
  echo "Usage: $0 --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> [--volume <name>] [--profile <name>]... [--template <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]" >&2
  echo "Try '$0 --help' for more information." >&2
  exit 1
}

show_help() {
  all_profile_names="$(profile_names | tr '\n' ' ')"
  volume_names="$(python3 -c "
import json
data = json.load(open('$GENERATE_ALL_CONFIG'))
print(' '.join(data.get('volumes', {}).keys()))
")"
  cat <<EOF
Usage: $0 --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> [--volume <name>] [--profile <name>]... [--template <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]

Run generator.py + tools/split_stream.sh in series for every (profile,
template) pair below, one continuous run per pair.

Options:
  --out <dir>              Output root. Each pair is written to
                           <dir>/<profile>/<template>/<volume>/YYYY/MM/DD/.
                           Required.
  --start <instant>        Passed straight through to every generator.py
                           run's -s, e.g. 2026-07-01T00:00:00. Required.
  --duration <duration>    Passed straight through to every generator.py
                           run's -r, e.g. P31D or P1M (see generator.py
                           --help for what -r accepts). Required.
  --volume <name>          Target output volume: overrides each profile's
                           own -i/-w with the settings recorded for it in
                           tools/generate_all.json, and becomes a path segment
                           in the output directory. A profile with no entry
                           for this volume is skipped, not an error. Default:
                           "default" — neither -i nor -w is passed to
                           generator.py at all, so it falls back to its own
                           bare defaults (DEFAULT_CONCURRENCY for -w, the
                           config's own interarrival rate for -i).
                           Valid names: $volume_names
  --profile <name>         Only this profile; repeatable. Default: all of them.
                           Valid names: $all_profile_names
  --template <name>        Only this template, within whichever profiles are
                           selected; repeatable. Default: every template a
                           selected profile has.
  --partition <duration>   ISO 8601 partition size, passed to -p. Default: P1D.
  --seed <n>               Passed to every generator.py run as --seed.
  --no-schedule            Skip each profile's schedule file, if it has one.
  --dry-run                Print the plan — every (profile, template) pair,
                           its output path, and the exact generator.py
                           command — without running anything.
  -h, --help               Show this help and exit.

Every profile's config file, schedule, template list, and per-volume -i/-w
settings live in tools/generate_all.json, not discovered from
presets/configs/*.json at runtime — a volume's -i/-w needs a human to have
actually benchmarked it first (see docs/how-to-build-a-config.md). Adding a
new preset means adding an entry there too.

Example:
  $0 --out out/lake --start 2026-05-27T00:00:00 --duration P3D --profile vpc_flow_logs --volume tiny
  $0 --out out/lake --start 2026-05-27T00:00:00 --duration P3D --profile zscaler_web --volume medium
  $0 --out out/lake --start 2026-05-27T00:00:00 --duration P3D --profile vpc_flow_logs
EOF
  exit 0
}

out_dir=""
start=""
duration=""
partition="P1D"
seed=""
no_schedule=0
dry_run=0
volume=""
want_profiles=()
want_templates=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out_dir="$2"; shift 2 ;;
    --start) start="$2"; shift 2 ;;
    --duration) duration="$2"; shift 2 ;;
    --profile) want_profiles+=("$2"); shift 2 ;;
    --template) want_templates+=("$2"); shift 2 ;;
    --volume) volume="$2"; shift 2 ;;
    --partition) partition="$2"; shift 2 ;;
    --seed) seed="$2"; shift 2 ;;
    --no-schedule) no_schedule=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) show_help ;;
    *) usage ;;
  esac
done

[[ -n "$out_dir" && -n "$start" && -n "$duration" ]] || usage

# $1: the value to check. $2..: the wanted-list array, expanded by the caller
# (bash 3.2 can't pass arrays by name) — empty means "everything matches".
in_list_or_empty() {
  local needle="$1"; shift
  [[ $# -eq 0 ]] && return 0
  for v in "$@"; do [[ "$v" == "$needle" ]] && return 0; done
  return 1
}

# Prints "<i> <w>" for a profile/volume pair from tools/generate_all.json, or
# fails (no output, non-zero exit) if that profile has no entry for this volume
# — a profile that can't reach a given volume is simply skipped, not an error,
# per "if the generator cannot support a particular output size, don't offer it."
volume_settings() {
  python3 -c "
import json, sys
data = json.load(open('$GENERATE_ALL_CONFIG'))
entry = data.get('profiles', {}).get('$1', {}).get('volumes', {}).get('$2')
if entry is None:
    sys.exit(1)
print(entry['i'], entry['w'])
"
}

run_count=0
while IFS= read -r profile; do
  in_list_or_empty "$profile" "${want_profiles[@]+"${want_profiles[@]}"}" || continue

  if [[ -n "$volume" ]]; then
    if ! read -r interval w < <(volume_settings "$profile" "$volume"); then
      echo "skipping $profile: no '$volume' volume defined for it in $GENERATE_ALL_CONFIG" >&2
      continue
    fi
    volume_label="$volume"
  else
    # No --volume: pass neither -i nor -w, so generator.py falls back to its own
    # bare defaults — deliberately distinct from any named volume's tuned settings.
    interval="-"
    w="-"
    volume_label="default"
  fi
  read -r config_file schedule < <(profile_settings "$profile")

  # Built with += rather than assigning "${maybe_empty_array[@]}" into another array
  # literal — bash 3.2 (the macOS system default) errors on expanding an empty array
  # under `set -u`, a bug fixed in bash 4.4+ that this script can't assume is present.
  base_cmd=(python generator.py -c "$CONFIG_DIR/$config_file" -r "$duration" -s "$start" -p "$partition")
  if [[ "$schedule" != "-" && $no_schedule -eq 0 ]]; then
    base_cmd+=(--schedule "$SCHEDULE_DIR/$schedule")
  fi
  [[ "$interval" != "-" ]] && base_cmd+=(-i "$interval")
  [[ "$w" != "-" ]] && base_cmd+=(-w "$w")
  [[ -n "$seed" ]] && base_cmd+=(--seed "$seed")

  while IFS='=' read -r template ext; do
    [[ -n "$template" ]] || continue
    in_list_or_empty "$template" "${want_templates[@]+"${want_templates[@]}"}" || continue
    slug="$(printf '%s' "$template" | tr -c 'A-Za-z0-9' '_')"
    dest="$out_dir/$profile/$slug/$volume_label"
    run_count=$((run_count + 1))

    cmd=("${base_cmd[@]}" -t "$template")

    if [[ $dry_run -eq 1 ]]; then
      echo "[$profile :: $template] -> $dest"
      echo "  ${cmd[*]}"
      continue
    fi

    echo "=== [$profile :: $template] -> $dest ===" >&2
    "$REPO_ROOT/tools/split_stream.sh" --out "$dest" --prefix "$profile-$slug" --ext "$ext" -- "${cmd[@]}"
  done < <(templates_for "$profile")
done < <(profile_names)

echo "" >&2
if [[ $dry_run -eq 1 ]]; then
  echo "dry-run: $run_count (profile, template) pairs would run" >&2
else
  echo "done: $run_count (profile, template) pairs processed" >&2
fi
