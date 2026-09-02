import argparse
import json
import logging
import random
import sys
from datetime import datetime
import dateutil.parser
import numpy as np
from ieg.core import DataDriver

logger = logging.getLogger('ieg')

DEFAULT_CONCURRENCY = 100

# -w now bounds a plain admitted-session counter, not OS threads -- there's no
# thread-creation ceiling to guard against any more (see ieg/core.py's
# Clock/session_process/arrival_process, migrated off one-OS-thread-per-session
# onto a single-threaded simpy event loop). This is a sanity bound against
# fat-fingered input and genuinely unbounded memory growth for a config whose
# natural ceiling is absurdly high, not a measured hardware limit.
MAX_WORKERS = 1000000

def validate_concurrency(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"-w must be an integer between 1 and {MAX_WORKERS}.")
    if ivalue < 1 or ivalue > MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"-w must be an integer between 1 and {MAX_WORKERS}.")
    return ivalue

def validate_start_interval(value):
    try:
        fvalue = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Start interval must be a number.")
    if fvalue < 0:
        raise argparse.ArgumentTypeError("Start interval must be greater than or equal to 0.")
    return fvalue

def apply_start_interval_override(config, override_value):
    """Override the event:start:timer state's cardinality_distribution in place.

    Each supported distribution type has a different field that governs the
    average interarrival period, so the override target is dispatched explicitly
    per type rather than inferred:
      - constant: 'value' (every worker waits exactly this long)
      - exponential, normal: 'mean'
      - gmm_temporal: 'mean' (the base period; the time-of-day 'days' shape is untouched)
    Anything else (e.g. 'uniform', which has no single central-tendency field) is
    unsupported and raises, rather than silently no-op'ing on a field that isn't read.
    """
    states = config.get('states', [])
    timer_state = next((s for s in states if s.get('type') == 'event:start:timer'), None)
    if timer_state is None:
        raise ValueError("Config has no event:start:timer state; cannot apply -i override.")

    dist = timer_state.get('cardinality_distribution', {})
    dist_type = dist.get('type')
    if dist_type == 'constant':
        field = 'value'
    elif dist_type in ('exponential', 'normal', 'gmm_temporal'):
        field = 'mean'
    else:
        raise ValueError(
            f"-i does not support the event:start:timer state's cardinality_distribution "
            f"type '{dist_type}'. Supported types: constant, exponential, normal, gmm_temporal."
        )

    original_value = dist.get(field)
    logger.warning("Over-riding preset start mean %s with %s.", original_value, override_value)
    dist[field] = override_value

def main(argv=None):
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        stream=sys.stderr
    )
    logger.setLevel(logging.INFO)
    logger.info("Starting synthetic event data generator")
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generates synthetic event data.')
    parser.add_argument('-c', dest='config_file', required=True, help='Generator configuration file')

    parser.add_argument('-t', '--template', dest='template_name', default=None,
                        help='Named template from the generator config\'s "templates" block.')

    parser.add_argument(
        '-s',
        dest='start_time',
        help='Specify the start time for the clock (ISO 8601 format). Defaults to the current time if not specified.'
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-r', dest='time', help='Length of time to generate data (may not be used with -n)')
    group.add_argument('-n', dest='n_recs', help='Number of records to generate (may not be used with -r)')

    parser.add_argument(
        '-w', '-m',
        dest='concurrency',
        type=validate_concurrency,
        nargs='?',
        default=DEFAULT_CONCURRENCY,
        help=f'Max entities (workers) concurrently generating events (1-{MAX_WORKERS}). '
             f'-m alias will be removed in future versions.'
    )

    parser.add_argument(
        '--schedule',
        dest='schedule_file',
        default=None,
        help='Schedule file (JSON) for modulating max_entities over time. Defaults to full capacity if not specified.'
    )

    parser.add_argument(
        '-i',
        dest='start_interval',
        type=validate_start_interval,
        default=None,
        help="Override the event:start:timer state's interarrival period (seconds), e.g. 0.1 = one worker "
             "dispatched every 1/10s, 5 = one worker every 5s. Overrides the preset's own value."
    )

    parser.add_argument(
        '-p', '--partition',
        dest='partition_interval',
        default=None,
        help='Emit a partition marker (and re-emit the template header, if any) to stdout at '
             'every calendar-aligned ISO 8601 duration boundary of simulated time, e.g. P1D for '
             'midnight-to-midnight days, PT1H for the top of every hour — like SQL TIME_TRUNC, '
             'not an offset from -s. Lets a downstream tool (see tools/split_stream.sh) split '
             'the stream into per-partition files with csplit, without parsing timestamps out '
             'of the rendered records themselves. The first partition may be shorter than one '
             'interval if -s does not itself fall on a boundary.'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help='Enable debug logging (written to stderr)'
    )
    
    parser.add_argument(
      '--seed',
        dest='seed',
        type=int,
        default=None,
        help='Random seed for deterministic data generation. Use with -s (simulated time) for fully reproducible output.'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        default=False,
        help='Validate the configuration file and exit without generating data.'
    )

    args = parser.parse_args(argv)

    # Configure logging level based on --debug flag
    if args.debug:
        logging.getLogger('ieg').setLevel(logging.DEBUG)
    # Seed random number generators for deterministic output
    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)

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

        if args.start_interval is not None:
            apply_start_interval_override(config, args.start_interval)

        # --validate: run pre-flight checks and exit
        if args.validate:
            from ieg.validate import validate_config
            if not validate_config(config, template_name=args.template_name):
                logger.critical("Config '%s' is invalid — see errors above.", args.config_file)
                sys.exit(1)
            sys.exit(0)

        # Load schedule file
        schedule_config = None
        if args.schedule_file:
            with open(args.schedule_file, 'r') as f:
                try:
                    schedule_config = json.load(f)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Error parsing schedule file '{args.schedule_file}': {e}")
            from ieg.distributions import Schedule
            if not Schedule.validate_desc(schedule_config, f"schedule '{args.schedule_file}'"):
                logger.critical("Schedule '%s' is invalid — see errors above.", args.schedule_file)
                sys.exit(1)

        # Start a new data driver
        driver = DataDriver(
            name='cli',
            config=config,
            runtime=runtime,
            total_recs=total_recs,
            time_type=time_type,
            start_time=start_time,
            max_entities=max_entities,
            schedule_config=schedule_config,
            template_name=args.template_name,
            partition_interval=args.partition_interval
        )
        logger.info("Starting synthetic event data generator at %s", datetime.now().isoformat())
        driver.simulate()

    except FileNotFoundError as e:
        logger.error("File error: %s", e)
        sys.exit(1)

    except ValueError as e:
        logger.error("Value error: %s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("Runtime error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("An unexpected error occurred: %s", e)
        sys.exit(1)
    logger.info("Synthetic event data generation completed")

if __name__ == "__main__":
    main()
