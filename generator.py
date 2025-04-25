import argparse
import json
import os
import sys
from datetime import datetime
import dateutil.parser
from ieg.core import DataDriver

DEFAULT_CONCURRENCY = 100

def main():

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generates synthetic event data.')
    parser.add_argument('-c', dest='config_file', required=True, help='Generator configuration file')
    parser.add_argument('-t', dest='target_file', help='Target configuration file')
    parser.add_argument('-f', dest='record_format_file', help='Format file for record pattern.')

    parser.add_argument(
        '-s',
        dest='start_time',
        help='Specify the start time for the clock (ISO 8601 format). Defaults to the current time if not specified.'
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-r', dest='time', help='Length of time to generate data (may not be used with -n)')
    group.add_argument('-n', dest='n_recs', help='Number of records to generate (may not be used with -r)')

    parser.add_argument(
        '-m',
        dest='concurrency',
        nargs='?',
        default=DEFAULT_CONCURRENCY,
        help='Max entities concurrently generating events'
    )

    args = parser.parse_args()

    # Determine start_time and time_type
    if args.start_time:
        try:
            start_time = dateutil.parser.isoparse(args.start_time)
            time_type = 'SIM'  # Simulated time when start_time is explicitly provided
        except ValueError as e:
            raise ValueError(f"Invalid start time format: {args.start_time}. Ensure it is in ISO 8601 format.") from e
    else:
        start_time = datetime.now()
        time_type = 'REAL'  # Real time when start_time is not provided

    runtime = args.time
    max_entities = int(args.concurrency)  # Convert to integer. Safe as there is a default.
    total_recs = int(args.n_recs) if args.n_recs else None

    try:
        # Load configuration file
        with open(args.config_file, 'r') as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Error parsing config file '{args.config_file}': {e}")

        # Load target file or use target from config
        if args.target_file:
            with open(args.target_file, 'r') as f:
                try:
                    target = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Error parsing target file '{args.target_file}': {e}")
        elif 'target' in config.keys():
            target = config['target']
        else:
            raise ValueError("No target specified in the config file or as a separate target file.")

        # Load record format file
        if args.record_format_file:
            if os.path.exists(args.record_format_file):
                try:
                    with open(args.record_format_file, 'r') as f:
                        # Interpret escape sequences like \t
                        record_format = f.read().strip().encode('utf-8').decode('unicode_escape')
                except UnicodeDecodeError as e:
                    raise ValueError(f"Error decoding record format file '{args.record_format_file}': {e}")
            else:
                raise FileNotFoundError(f"Record format file '{args.record_format_file}' not found. Ensure the file path is correct.")
        else:
            record_format = None

        # Start a new data driver
        driver = DataDriver(
            name='cli',
            config=config,
            target=target,
            runtime=runtime,
            total_recs=total_recs,
            time_type=time_type,
            start_time=start_time,
            max_entities=max_entities,
            record_format=record_format
        )
        driver.simulate()

    except FileNotFoundError as e:
        print(f"File error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Value error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
