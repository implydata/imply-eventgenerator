#!/usr/bin/env bash
#
# Run generator.py + tools/split_stream.sh in series for every (profile, template)
# pair below, one continuous run per pair covering the whole --start/--end range.
# This is the middle ground between a single tools/split_stream.sh call and the
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
#
# Usage:
#   tools/generate_all.sh --out <dir> --start <YYYY-MM-DD> --end <YYYY-MM-DD> \
#     [--profile <name>]... [--partition <ISO8601 duration>] [--seed <n>] [--no-schedule] [--dry-run]
#
# Example:
#   tools/generate_all.sh --out out/lake --start 2026-05-27 --end 2026-05-29 --profile vpc_flow_logs
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="$REPO_ROOT/presets/configs"
SCHEDULE_DIR="$REPO_ROOT/presets/schedules"

# profile | config file (relative to presets/configs) | -w ceiling | schedule file (or "-")
PROFILES=(
  "ecommerce|ecommerce.json|2112|ecommerce.json"
  "ecommerce_lighting|ecommerce_lighting.json|2112|ecommerce.json"
  "ecommerce_furniture|ecommerce_furniture.json|528|ecommerce.json"
  "vpc_flow_logs|vpc_flow_logs.json|66|-"
  "vpc_flow_logs_derived|vpc_flow_logs_derived.json|1056|-"
  "endpoint_network|endpoint_network.json|1|-"
  "ssh_auth|ssh_auth.json|66|-"
  "pbx_calls|pbx_calls.json|9|-"
  "palo_alto|palo_alto.json|66|-"
  "zscaler_web|zscaler_web.json|33|-"
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
  echo "Usage: $0 --out <dir> --start <YYYY-MM-DD> --end <YYYY-MM-DD> [--profile <name>]... [--partition <duration>] [--seed <n>] [--no-schedule] [--dry-run]" >&2
  exit 1
}

out_dir=""
start_date=""
end_date=""
partition="P1D"
seed=""
no_schedule=0
dry_run=0
want_profiles=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out_dir="$2"; shift 2 ;;
    --start) start_date="$2"; shift 2 ;;
    --end) end_date="$2"; shift 2 ;;
    --profile) want_profiles+=("$2"); shift 2 ;;
    --partition) partition="$2"; shift 2 ;;
    --seed) seed="$2"; shift 2 ;;
    --no-schedule) no_schedule=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ -n "$out_dir" && -n "$start_date" && -n "$end_date" ]] || usage

to_epoch() { date -d "$1" +%s 2>/dev/null || date -j -f "%Y-%m-%d" "$1" +%s; }
days=$(( ( $(to_epoch "$end_date") - $(to_epoch "$start_date") ) / 86400 + 1 ))
[[ $days -ge 1 ]] || { echo "error: --end is before --start" >&2; exit 1; }
runtime="P${days}D"
start_iso="${start_date}T00:00:00"

wanted() {
  [[ ${#want_profiles[@]} -eq 0 ]] && return 0
  for p in "${want_profiles[@]}"; do [[ "$p" == "$1" ]] && return 0; done
  return 1
}

run_count=0
for entry in "${PROFILES[@]}"; do
  IFS='|' read -r profile config_file w schedule <<< "$entry"
  wanted "$profile" || continue

  # Built with += rather than assigning "${maybe_empty_array[@]}" into another array
  # literal — bash 3.2 (the macOS system default) errors on expanding an empty array
  # under `set -u`, a bug fixed in bash 4.4+ that this script can't assume is present.
  base_cmd=(python generator.py -c "$CONFIG_DIR/$config_file" -w "$w" -r "$runtime" -s "$start_iso" -p "$partition")
  if [[ "$schedule" != "-" && $no_schedule -eq 0 ]]; then
    base_cmd+=(--schedule "$SCHEDULE_DIR/$schedule")
  fi
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
