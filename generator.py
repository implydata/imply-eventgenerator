import argparse
import json
import os
import sys
from datetime import datetime
import dateutil.parser
from ieg.core import DataDriver

def main():

    # Parse command line arguments

    parser = argparse.ArgumentParser(description='Generates synthetic event data.')
    parser.add_argument('-f', dest='config_file', nargs='?', help='the workload config file name')
    parser.add_argument('-o', dest='target_file', nargs='?', help='the message output target file name')
    parser.add_argument('-t', dest='time', nargs='?', help='the script runtime (may not be used with -n)')
    parser.add_argument('-n', dest='n_recs', nargs='?', help='the number of records to generate (may not be used with -t)')
    parser.add_argument('-s', dest='time_type', nargs='?', const='SIM', default='REAL', help='simulate time (default is real, not simulated)')
    parser.add_argument('-m', dest='concurrency', nargs='?', default=100, help='max entities concurrently generating events')
    parser.add_argument('-p', dest='global_pattern_file', nargs='?', help='the file containing the global pattern')

    args = parser.parse_args()
    runtime = args.time

    # Validate command line arguments

    max_entities = int(args.concurrency) # Convert to integer. Safe as there is a default.
    total_recs = None
    if args.n_recs is not None:
        total_recs = int(args.n_recs)
    time_type = args.time_type
    if time_type == 'SIM':
        start_time = datetime.now()
    elif time_type == 'REAL':
        start_time = datetime.now()
    else:
        start_time = dateutil.parser.isoparse(time_type)
        time_type = 'SIM'

    if (runtime is not None) and (total_recs is not None):
        print("Use either -t or -n, but not both")
        parser.print_help()
        exit()

    try:
        config_file_name = f'{args.config_file}'
        if config_file_name:
            with open(config_file_name, 'r') as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Error parsing config file '{config_file_name}': {e}")
        else:
            try:
                config = json.load(sys.stdin)
            except json.JSONDecodeError as e:
                raise ValueError(f"Error parsing config from stdin: {e}")
            
        target_file_name = args.target_file
        if target_file_name:
            with open(target_file_name, 'r') as f:
                try:
                    target = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Error parsing target file '{target_file_name}': {e}")
        elif 'target' in config.keys():
            target = config['target']
        else:
            raise ValueError("No target specified in the config file or as a separate target file.")

        global_pattern_file = args.global_pattern_file
        if global_pattern_file:
            if os.path.exists(global_pattern_file):
                try:
                    with open(global_pattern_file, 'r') as f:
                        # Interpret escape sequences like \t
                        global_pattern = f.read().strip().encode('utf-8').decode('unicode_escape')
                except UnicodeDecodeError as e:
                    raise ValueError(f"Error decoding global pattern file '{global_pattern_file}': {e}")
            else:
                raise FileNotFoundError(f"Global pattern file '{global_pattern_file}' not found. Ensure the file path is correct.")
        else:
            global_pattern = None

        # Start a new data driver

        driver = DataDriver(  # Use the explicitly imported DataDriver
            name='cli',
            config=config,
            target=target,
            runtime=runtime,
            total_recs=total_recs,
            time_type=time_type,
            start_time=start_time,
            max_entities=max_entities,
            global_pattern=global_pattern
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
