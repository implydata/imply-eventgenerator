#!/bin/bash
# vpc_flow_to_s3.sh
# Captures VPC flow log output from a generator and uploads to S3 daily,
# partitioned by year/month/day derived from the log data's own timestamps.
#
# Usage:
#   ./your_generator | ./vpc_flow_to_s3.sh
#   or
#   ./vpc_flow_to_s3.sh --generator "./your_generator"

# ── Configuration ────────────────────────────────────────────────────────────
S3_BUCKET="labs-sample-datasets"
S3_PREFIX="eventgen/vpc_flow_logs/aws_cloudwatchlogs_vpcflow/default"  # top-level folder; set to "" to write at bucket root
REGION="us-east-1"                 # change if your bucket is in a different region
AWS_PROFILE="imply-devrel"
export AWS_PROFILE
TMPDIR="/tmp/vpc-flow-staging"
FLUSH_INTERVAL=300                 # seconds between S3 uploads (5 min default)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

mkdir -p "$TMPDIR"

# If --generator flag is passed, exec that; otherwise read from stdin
if [[ "${1:-}" == "--generator" ]]; then
    exec "$2" | "$0"
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2; }

upload_file() {
    local filepath="$1"
    local date_path="$2"   # e.g. 2025/07/01

    local filename
    filename="$(basename "$filepath")"

    local s3_key
    if [[ -n "$S3_PREFIX" ]]; then
        s3_key="${S3_PREFIX}/${date_path}/${filename}"
    else
        s3_key="${date_path}/${filename}"
    fi

    log "Uploading $filepath → s3://${S3_BUCKET}/${s3_key}"
    aws s3 cp "$filepath" "s3://${S3_BUCKET}/${s3_key}" \
        --region "$REGION" \
        --content-encoding gzip \
        --content-type "text/plain"
    rm -f "$filepath"
}

flush_all() {
    # Upload every tmp file currently in the staging dir
    for tmpfile in "$TMPDIR"/vpc-flow-*.tmp; do
        [[ -f "$tmpfile" ]] || continue

        # Derive date_path from filename: vpc-flow-2025-07-01.tmp → 2025/07/01
        local base
        base=$(basename "$tmpfile" .tmp)    # vpc-flow-2025-07-01
        local datepart="${base#vpc-flow-}"  # 2025-07-01
        # Convert only the first two dashes to slashes: 2025/07/01
        local date_path
        date_path=$(echo "$datepart" | sed 's/-/\//;s/-/\//')

        local ts
        ts=$(date +%Y%m%d-%H%M%S)
        local gz_file="${tmpfile%.tmp}.${ts}.log.gz"
        gzip -c "$tmpfile" > "$gz_file"
        rm -f "$tmpfile"
        upload_file "$gz_file" "$date_path"
    done
}

# ── Main loop ────────────────────────────────────────────────────────────────
log "Starting VPC flow log capture → s3://${S3_BUCKET}/${S3_PREFIX}"
log "Partitioning by timestamp in log data (field 11)"

last_flush=$(date +%s)

while IFS= read -r line; do
    if [[ "$line" == version* ]]; then
        continue
    fi

    # Avoid forking awk — split on whitespace using bash itself
    read -r -a fields <<< "$line"
    log_epoch="${fields[10]}"   # field 11, 0-indexed

    if ! [[ "$log_epoch" =~ ^[0-9]+$ ]]; then
        continue
    fi

    # Only fork `date` when the epoch's calendar day actually changes
    day_bucket=$(( log_epoch / 86400 ))
    if [[ "$day_bucket" != "${last_day_bucket:-}" ]]; then
        log_date=$(date -u -d "@${log_epoch}" +%Y-%m-%d 2>/dev/null || date -u -r "${log_epoch}" +%Y-%m-%d)
        last_day_bucket="$day_bucket"
    fi

    current_file="${TMPDIR}/vpc-flow-${log_date}.tmp"
    echo "$line" >> "$current_file"

    # Periodic flush of all open tmp files
    now_epoch=$(date +%s)
    if (( now_epoch - last_flush >= FLUSH_INTERVAL )); then
        log "Flushing staged files to S3..."
        flush_all
        last_flush=$now_epoch
    fi

done

# ── Final flush on EOF ────────────────────────────────────────────────────────
log "Generator finished — flushing remaining files"
flush_all

log "Done."