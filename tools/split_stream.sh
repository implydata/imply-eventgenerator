#!/usr/bin/env bash
#
# Split a generator.py run into calendar-partitioned, gzipped files, using
# generator.py's own --partition marker as the split point — no timestamp parsing
# of the rendered records themselves, since presets render 11 different output
# shapes with no common field or format to parse generically. See
# docs/how-to-build-a-config.md and generator.py's own --help for -p/--partition.
#
# generator.py and csplit run as two independent background jobs connected by a
# named pipe (not a plain `|`), so each one's exit status can be checked
# separately — pipefail alone doesn't reliably cover a backgrounded pipeline. A
# third loop watches for each segment csplit finishes (signalled by the next
# numbered file appearing, since csplit writes them strictly in order) and
# gzips + deletes it immediately, rather than waiting for the whole run to
# finish before touching any output — peak disk is bounded to roughly one
# partition's raw size, not the entire run's.
set -euo pipefail

# Re-exec under caffeinate (macOS) so idle sleep can't interrupt a long run —
# a real, observed cause of hangs: the engine's threads block on an untimed
# threading.Event, and a disrupted sleep/wake cycle can lose the wakeup for
# good, with no recovery even once the machine is fully awake again. Guarded
# by an env var so this only wraps once, not on every re-exec.
if [[ -z "${SPLIT_STREAM_CAFFEINATED:-}" ]]; then
  export SPLIT_STREAM_CAFFEINATED=1
  if command -v caffeinate >/dev/null 2>&1; then
    exec caffeinate -i "$0" "$@"
  else
    echo "warning: caffeinate not found — this run has no protection against idle sleep interrupting it mid-way, which has caused real hangs on long runs. caffeinate ships with macOS by default; on other platforms, make sure your own power/sleep settings won't interrupt a multi-hour run." >&2
  fi
fi

MARKER_PREFIX=$'\x1ePARTITION '

usage() {
  echo "Usage: $0 --out <dir> [--prefix <name>] [--ext <ext>] -- <generator.py command...>" >&2
  echo "Try '$0 --help' for more information." >&2
  exit 1
}

show_help() {
  cat <<EOF
Usage: $0 --out <dir> [--prefix <name>] [--ext <ext>] -- <generator.py command...>

Run a generator.py command and split its stdout into calendar-partitioned,
gzipped files, using the "\x1ePARTITION <ISO timestamp>" marker generator.py
emits when run with -p/--partition. Each split segment's first line is the
marker itself, so its own boundary timestamp names the file — no reformatting.
Segments are gzipped and cleaned up as each one completes, not all at once at
the end, so peak disk usage stays bounded to roughly one partition's raw size
regardless of how long the overall run is.

Options:
  --out <dir>        Output root. Files are written to
                     <dir>/YYYY/MM/DD/<prefix->stamp.ext.gz. Required.
  --prefix <name>    Prefix for each output filename, e.g. profile-template.
                     Optional; omit for just <stamp>.ext.gz.
  --ext <ext>        File extension before .gz, e.g. json, csv, log. Default: log.
  -h, --help         Show this help and exit.

Everything after -- is the generator.py command to run. It must itself
include -p/--partition — without it, stdout has no marker to split on, and
this script fails with a clear error rather than silently writing the whole
run as one file.

Requires GNU csplit. The BSD csplit that ships by default on macOS lacks
features this script needs; install GNU coreutils (brew install coreutils
on macOS) and it's picked up automatically as 'gcsplit'.

On macOS, this script re-execs itself under caffeinate -i automatically, so
idle sleep can't interrupt a long run — a real, observed cause of hangs the
engine has no recovery from. If caffeinate isn't found (e.g. non-macOS),
a warning is printed and the run proceeds unprotected.

Example:
  $0 --out out/vpc_flow_logs --prefix vpc_flow_logs-aws_cloudwatchlogs_vpcflow --ext log -- \\
    python generator.py -c presets/configs/vpc_flow_logs.json -t aws:cloudwatchlogs:vpcflow \\
      -w 66 -r P7D -s 2026-05-27T00:00:00 -p P1D
EOF
  exit 0
}

out_dir=""
prefix=""
ext="log"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out_dir="$2"; shift 2 ;;
    --prefix) prefix="$2"; shift 2 ;;
    --ext) ext="$2"; shift 2 ;;
    -h|--help) show_help ;;
    --) shift; break ;;
    *) usage ;;
  esac
done

[[ -n "$out_dir" ]] || usage
[[ $# -gt 0 ]] || usage

find_csplit() {
  command -v gcsplit >/dev/null 2>&1 && { echo gcsplit; return; }
  command -v csplit >/dev/null 2>&1 && csplit --version 2>/dev/null | grep -q 'GNU coreutils' && { echo csplit; return; }
  return 1
}

CSPLIT="$(find_csplit)" || {
  echo "error: GNU csplit is required (the BSD csplit that ships by default on macOS lacks features this script needs)." >&2
  case "$(uname -s)" in
    Darwin) echo "Install it with:  brew install coreutils   (provides 'gcsplit')" >&2 ;;
    Linux)  echo "Install GNU coreutils via your package manager, e.g. apt/dnf/apk install coreutils" >&2 ;;
    *)      echo "Install GNU coreutils for your platform." >&2 ;;
  esac
  exit 1
}

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

part_path() { printf '%s/part_%05d' "$work_dir" "$1"; }

# Gzip, place, and clean up one completed segment. Only called once the NEXT-
# numbered segment exists (proving csplit has moved past this one) or, for the
# very last segment, once csplit itself has exited.
process_part() {
  local part
  part="$(part_path "$1")"
  if [[ ! -s "$part" ]]; then
    rm -f "$part"  # a leading zero-byte segment, if csplit produced one
    return 0
  fi

  local first_line ts
  first_line="$(head -n 1 "$part")"
  case "$first_line" in
    "${MARKER_PREFIX}"*)
      ts="${first_line#"$MARKER_PREFIX"}"
      tail -n +2 "$part" > "$part.body"
      ;;
    *)
      echo "error: $part does not start with a partition marker — was -p/--partition set on the generator command?" >&2
      exit 1
      ;;
  esac

  local year="${ts:0:4}" month="${ts:5:2}" day="${ts:8:2}" compact
  compact="${ts:0:19}"
  compact="${compact//[-:]/}"

  local dest_dir="$out_dir/$year/$month/$day"
  mkdir -p "$dest_dir"
  local dest="$dest_dir/${prefix:+$prefix-}$compact.$ext.gz"

  gzip -c "$part.body" > "$dest.partial"
  mv "$dest.partial" "$dest"
  rm -f "$part" "$part.body"
  written=$((written + 1))
  echo "wrote $dest" >&2
}

fifo="$work_dir/stream"
mkfifo "$fifo"

# The marker line is kept (no --suppress-matched), not discarded, since it
# carries the partition's own boundary timestamp — segment N's first line
# always labels it. generator.py and csplit are two independent background
# jobs (not one foreground pipe) specifically so each one's exit status can be
# checked on its own below.
"$@" > "$fifo" &
gen_pid=$!
"$CSPLIT" -s -f "$work_dir/part_" -b '%05d' - "/^${MARKER_PREFIX}/" '{*}' < "$fifo" &
csplit_pid=$!

written=0
next=0
while kill -0 "$csplit_pid" 2>/dev/null; do
  while [[ -e "$(part_path $((next + 1)))" ]]; do
    process_part "$next"
    next=$((next + 1))
  done
  sleep 1
done

gen_status=0
csplit_status=0
wait "$gen_pid" || gen_status=$?
wait "$csplit_pid" || csplit_status=$?
[[ $gen_status -eq 0 ]] || { echo "error: generator command exited $gen_status" >&2; exit 1; }
[[ $csplit_status -eq 0 ]] || { echo "error: $CSPLIT exited $csplit_status" >&2; exit 1; }

# csplit has now fully exited, so every remaining segment — including the
# last one, which only becomes complete once the whole stream ends, not when
# some "next" file appears — is safe to process.
while [[ -e "$(part_path "$next")" ]]; do
  process_part "$next"
  next=$((next + 1))
done

echo "done: $written partitions written to $out_dir" >&2
