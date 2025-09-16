#!/bin/bash

while true; do
  START_TIME="2025-08-28T08:00"
  echo "$(date '+%Y-%m-%d %H:%M:%S') Running generator... with start time: $START_TIME"

  python3 generator.py \
    -c conf/gen/apache_access_combined.json \
    -f conf/form/hec_apache_access_combined.txt \
    -t conf/tar/hec_file.json \
    -m 500 \
    -s "$START_TIME" \
    -r PT1H

  echo "$(date '+%Y-%m-%d %H:%M:%S') Sending logs to Splunk..."
  python3 otel_splunk_pipeline.py hec_access_combined.json

  echo "$(date '+%Y-%m-%d %H:%M:%S') Cycle complete. Restarting..."
  sleep 30
done
