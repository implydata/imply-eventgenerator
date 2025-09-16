import json
import requests
import uuid
import time
import re
import sys

OTLP1_ENDPOINT = "http://localhost:4318/v1/logs"  
OTLP2_ENDPOINT = "http://localhost:4319/v1/logs"  

def send_log(json_obj):
    now_nano = int(time.time() * 1e9)

    # Split out the "event" field as body
    event_body = json_obj.get("event", "")
    attributes = []

    # Move other top-level keys to attributes
    for key, value in json_obj.items():
        if key != "event":
            attr_type = "stringValue" if isinstance(value, str) else \
                        "intValue" if isinstance(value, int) else \
                        "doubleValue" if isinstance(value, float) else \
                        "boolValue" if isinstance(value, bool) else "stringValue"
            attributes.append({
                "key": key,
                "value": {attr_type: str(value) if attr_type.endswith("Value") else value}
            })

    # Add a log_id for tracing
    attributes.append({
        "key": "log_id",
        "value": {"stringValue": str(uuid.uuid4())}
    })

    log_record = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "json-log-sender"}}
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "manual-log-sender"},
                        "logRecords": [
                            {
                                "timeUnixNano": str(now_nano),
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "body": {"stringValue": event_body},  # ONLY the event string here
                                "attributes": attributes
                            }
                        ]
                    }
                ]
            }
        ]
    }

    response1 = requests.post(OTLP1_ENDPOINT, json=log_record)
    response2 = requests.post(OTLP2_ENDPOINT, json=log_record)
    if response1.status_code != 200: 
        print("Failed to send log")
        # Print the response for debugging
        try:
            error_info = f"resp1: {response1.json()} resp2: {response2.json()}" 
            print(f"Error details: {error_info}")
        except: 
            print("Failed. No response text available")
    time.sleep(0.03)  # Rate limit to avoid overwhelming the server

def safe_json_load(line):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        pass

    # Fix malformed event field with embedded quotes
    start = line.find('"event"')
    open_quote = line.find('"', start + len('"event":'))
    if open_quote == -1:
        return None

    i = open_quote + 1
    escaped = False
    while i < len(line):
        if line[i] == '"' and not escaped and (i + 1 >= len(line) or line[i+1] in [',', '}']):
            break
        escaped = (line[i] == '\\' and not escaped)
        i += 1
    else:
        return None

    raw_event_value = line[open_quote+1:i]
    escaped_event = raw_event_value.replace('\\', '\\\\').replace('"', '\\"')
    fixed_line = line[:open_quote+1] + escaped_event + line[i:]

    try:
        return json.loads(fixed_line)
    except json.JSONDecodeError:
        return None
        
def send_file(file_path):
    with open(file_path) as f:
        for line in f:
            try:
                line = line.replace("+00:00", "+0000")
                obj = safe_json_load(line)
                if obj is None:
                    print("Obj is None: Skipping invalid JSON line")
                    continue
                send_log(obj)
            except json.JSONDecodeError:
                print("Exception: Skipping invalid JSON line")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python send_logs.py path/to/file.jsonl")
        sys.exit(1)
    send_file(sys.argv[1])
