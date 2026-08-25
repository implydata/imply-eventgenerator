#!/usr/bin/env bash
#
# Split a generator.py run into calendar-partitioned, gzipped files, using
# generator.py's own --partition marker as the split point — no timestamp parsing
# of the rendered records themselves, since presets render 11 different output
# shapes with no common field or format to parse generically. See
# docs/how-to-build-a-config.md and generator.py's own --help for -p/--partition.
set -euo pipefail

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

Example:
  $0 --out out/vpc_flow_logs --prefix vpc_flow_logs-aws_cloudwatchlogs_vpcflow --ext log -- \\
    python generator.py -c presets/configs/vpc_flow_logs.json -t aws:cloudwatchlogs:vpcflow \\
      -w 66 -r P7D -s 2026-05-27T00:00:00 -p P1D --seed 42
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

# The marker line is kept (no --suppress-matched), not discarded, since it carries
# the partition's own boundary timestamp — segment N's first line always labels it.
"$@" | "$CSPLIT" -s -f "$work_dir/part_" -b '%05d' - "/^${MARKER_PREFIX}/" '{*}'

written=0
for part in "$work_dir"/part_*; do
  [[ -s "$part" ]] || continue  # a leading zero-byte segment, if csplit produced one

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

  year="${ts:0:4}"
  month="${ts:5:2}"
  day="${ts:8:2}"
  compact="${ts:0:19}"
  compact="${compact//[-:]/}"

  dest_dir="$out_dir/$year/$month/$day"
  mkdir -p "$dest_dir"
  dest="$dest_dir/${prefix:+$prefix-}$compact.$ext.gz"

  gzip -c "$part.body" > "$dest.partial"
  mv "$dest.partial" "$dest"
  written=$((written + 1))
  echo "wrote $dest" >&2
done

echo "done: $written partitions written to $out_dir" >&2
