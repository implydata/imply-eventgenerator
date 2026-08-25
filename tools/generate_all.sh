#!/usr/bin/env bash
#
# Run generator.py + tools/split_stream.sh in series for every (profile, template)
# pair below, one continuous run per pair. --start/--duration pass straight through
# to generator.py's own -s/-r with no transformation, so this stays a thin wrapper
# rather than a second date-range convention to learn. This is the middle ground
# between a single tools/split_stream.sh call and the
# fuller tools/generate_lake.py (per-day subprocesses, parallel jobs, direct S3
# upload, resume manifest) — use this for a straightforward, sequential local lake
# build; use generate_lake.py when you need parallelism or S3 upload with resume.
#
# The (profile, template, -w ceiling, schedule, extension) table below is hardcoded
# on purpose, not discovered from presets/configs/*.json at runtime — ceilings need
# a human to have run tools/bench_config_workers.py first (see docs/how-to-build-a-config.md),
# same as tools/generate_lake.py's PROFILE_SETTINGS. Adding a new preset means adding
# a line here too — see the "Add config and templates to tools/generate_all.sh" step in
# docs/how-to-build-a-config.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$REPO_ROOT/presets/configs"
SCHEDULE_DIR="$REPO_ROOT/presets/schedules"

# profile | config file (relative to presets/configs) | -w ceiling | schedule file (or "-")
# | -i interval override (or "-" for the config's own default)
#
# -w alone only raises throughput up to the natural ceiling for whatever interarrival
# rate is in effect (Little's Law: L = lambda*W) — past that, only lowering -i (raising
# lambda) raises the ceiling itself, and -w has to rise to match or it just re-throttles
# at the new ceiling. Values below are the profile's own default; -i/-w pairs that
# deliberately push volume higher are measured in docs/presets/<profile>.md's grid, not
# guessed — see zscaler_web's -i 0.1/-w 250 (~15x its default volume) as the example.
PROFILES=(
  "ecommerce|ecommerce.json|2112|ecommerce.json|-"
  "ecommerce_lighting|ecommerce_lighting.json|2112|ecommerce.json|-"
  "ecommerce_furniture|ecommerce_furniture.json|528|ecommerce.json|-"
  "vpc_flow_logs|vpc_flow_logs.json|66|-|-"
  "vpc_flow_logs_derived|vpc_flow_logs_derived.json|1056|-|-"
  "endpoint_network|endpoint_network.json|1|-|-"
  "ssh_auth|ssh_auth.json|66|-|-"
  "pbx_calls|pbx_calls.json|9|-|-"
  "palo_alto|palo_alto.json|66|-|-"
  "zscaler_web|zscaler_web.json|250|-|0.1"
)

# template=extension, one block per profile — kept fully separate per profile, even
# where identical today, since the ecommerce configs are independent (CLAUDE.md).
# A function + case (not an associative array) so this runs on bash 3.2, the macOS
# system default, without requiring a newer bash as an extra dependency.
templates_for() {
  case "$1" in
    ecommerce) cat <<'EOF'
apache:access:json=json
apache:access:kv=log
apache:access:combined=log
access_combined=log
access_combined_wcookie=log
access_common=log
csv=csv
ms:iis:auto=log
ms:iis:default:85=log
ms:iis:default=log
ms:iis:splunk=log
ocsf:http_activity=json
EOF
      ;;
    ecommerce_lighting) cat <<'EOF'
apache:access:json=json
apache:access:kv=log
apache:access:combined=log
access_combined=log
access_combined_wcookie=log
access_common=log
csv=csv
ms:iis:auto=log
ms:iis:default:85=log
ms:iis:default=log
ms:iis:splunk=log
ocsf:http_activity=json
EOF
      ;;
    ecommerce_furniture) cat <<'EOF'
apache:access:json=json
apache:access:kv=log
apache:access:combined=log
access_combined=log
access_combined_wcookie=log
access_common=log
csv=csv
ms:iis:auto=log
ms:iis:default:85=log
ms:iis:default=log
ms:iis:splunk=log
ocsf:http_activity=json
EOF
      ;;
    vpc_flow_logs) cat <<'EOF'
aws:cloudwatchlogs:vpcflow=log
ocsf:network_activity=json
EOF
      ;;
    vpc_flow_logs_derived) cat <<'EOF'
aws:cloudwatchlogs:vpcflow=log
EOF
      ;;
    endpoint_network) cat <<'EOF'
WindowsFirewallLog=log
ocsf:network_activity=json
EOF
      ;;
    ssh_auth) cat <<'EOF'
linux_secure=log
ocsf:authentication=json
EOF
      ;;
    pbx_calls) cat <<'EOF'
asterisk_cdr=log
EOF
      ;;
    palo_alto) cat <<'EOF'
pan:syslog=log
compact=json
EOF
      ;;
    zscaler_web) cat <<'EOF'
zscalernss-web=log
ocsf:http_activity=json
EOF
      ;;
    *)
      echo "error: no template list for profile '$1'" >&2
      exit 1
      ;;
  esac
}

usage() {
  echo "Usage: $0 --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> [--profile <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]" >&2
  echo "Try '$0 --help' for more information." >&2
  exit 1
}

show_help() {
  profile_names=""
  for entry in "${PROFILES[@]}"; do
    profile_names="$profile_names ${entry%%|*}"
  done
  cat <<EOF
Usage: $0 --out <dir> --start <ISO8601 instant> --duration <ISO8601 duration> [--profile <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]

Run generator.py + tools/split_stream.sh in series for every (profile,
template) pair below, one continuous run per pair — the middle ground
between a single split_stream.sh call and the fuller tools/generate_lake.py
(parallel jobs, S3 upload, resume manifest).

Options:
  --out <dir>              Output root. Each pair is written to
                           <dir>/<profile>/<template>/YYYY/MM/DD/. Required.
  --start <instant>        Passed straight through to every generator.py
                           run's -s, e.g. 2026-07-01T00:00:00. Required.
  --duration <duration>    Passed straight through to every generator.py
                           run's -r, e.g. P31D or P1M (see generator.py
                           --help for what -r accepts). Required.
  --profile <name>         Only this profile; repeatable. Default: all of them.
                           Valid names:$profile_names
  --partition <duration>   ISO 8601 partition size, passed to -p. Default: P1D.
  --seed <n>               Passed to every generator.py run as --seed.
  --no-schedule            Skip each profile's schedule file, if it has one.
  --dry-run                Print the plan — every (profile, template) pair,
                           its output path, and the exact generator.py
                           command — without running anything.
  -h, --help               Show this help and exit.

The (profile, template, -w ceiling, schedule, extension) table this script
runs is hardcoded above, not discovered from presets/configs/*.json at
runtime — ceilings need a human to have run tools/bench_config_workers.py
first (see docs/how-to-build-a-config.md), same as generate_lake.py's
PROFILE_SETTINGS. Adding a new preset means adding a line here too.

Example:
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
want_profiles=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out_dir="$2"; shift 2 ;;
    --start) start="$2"; shift 2 ;;
    --duration) duration="$2"; shift 2 ;;
    --profile) want_profiles+=("$2"); shift 2 ;;
    --partition) partition="$2"; shift 2 ;;
    --seed) seed="$2"; shift 2 ;;
    --no-schedule) no_schedule=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) show_help ;;
    *) usage ;;
  esac
done

[[ -n "$out_dir" && -n "$start" && -n "$duration" ]] || usage

wanted() {
  [[ ${#want_profiles[@]} -eq 0 ]] && return 0
  for p in "${want_profiles[@]}"; do [[ "$p" == "$1" ]] && return 0; done
  return 1
}

run_count=0
for entry in "${PROFILES[@]}"; do
  IFS='|' read -r profile config_file w schedule interval <<< "$entry"
  wanted "$profile" || continue

  # Built with += rather than assigning "${maybe_empty_array[@]}" into another array
  # literal — bash 3.2 (the macOS system default) errors on expanding an empty array
  # under `set -u`, a bug fixed in bash 4.4+ that this script can't assume is present.
  base_cmd=(python generator.py -c "$CONFIG_DIR/$config_file" -w "$w" -r "$duration" -s "$start" -p "$partition")
  if [[ "$schedule" != "-" && $no_schedule -eq 0 ]]; then
    base_cmd+=(--schedule "$SCHEDULE_DIR/$schedule")
  fi
  [[ "$interval" != "-" ]] && base_cmd+=(-i "$interval")
  [[ -n "$seed" ]] && base_cmd+=(--seed "$seed")

  while IFS='=' read -r template ext; do
    [[ -n "$template" ]] || continue
    slug="$(printf '%s' "$template" | tr -c 'A-Za-z0-9' '_')"
    dest="$out_dir/$profile/$slug"
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
done

echo "" >&2
if [[ $dry_run -eq 1 ]]; then
  echo "dry-run: $run_count (profile, template) pairs would run" >&2
else
  echo "done: $run_count (profile, template) pairs processed" >&2
fi
