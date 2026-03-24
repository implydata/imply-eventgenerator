"""
This module provides utilities for parsing and handling distributions.

Distributions are used to generate random values based on specified probability
distributions. This module includes functions for parsing distribution configurations
and generating samples from them.
"""

import math
import numpy as np
import dateutil.parser

class DistConstant:
    """
    Represents a constant value distribution.
    """
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return 'DistConstant(value='+str(self.value)+')'
    def get_sample(self):
        """Return the constant value."""
        return self.value

    @staticmethod
    def validate_desc(desc, context):
        errors = []
        if 'value' not in desc:
            errors.append(f"{context}: constant distribution missing required field 'value'")
        return errors

class DistUniform:
    """
    Represents a uniform distribution between a minimum and maximum value.
    """
    def __init__(self, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
    def __str__(self):
        return 'DistUniform(min_value='+str(self.min_value)+', max_value='+str(self.max_value)+')'
    def get_sample(self):
        """Return a uniformly distributed random value between min and max."""
        return np.random.uniform(self.min_value, self.max_value+1)

    @staticmethod
    def validate_desc(desc, context):
        errors = []
        if 'min' not in desc:
            errors.append(f"{context}: uniform distribution missing required field 'min'")
        if 'max' not in desc:
            errors.append(f"{context}: uniform distribution missing required field 'max'")
        if 'min' in desc and 'max' in desc:
            try:
                if float(desc['min']) > float(desc['max']):
                    errors.append(f"{context}: uniform distribution 'min' ({desc['min']}) must be <= 'max' ({desc['max']})")
            except (TypeError, ValueError):
                pass  # type errors will surface at runtime
        return errors

class DistExponential:
    """
    Represents an exponential distribution with a given mean.
    """
    def __init__(self, mean):
        self.mean = mean
    def __str__(self):
        return 'DistExponential(mean='+str(self.mean)+')'
    def get_sample(self):
        """Return an exponentially distributed random value with the configured mean."""
        return np.random.exponential(scale=self.mean)

    @staticmethod
    def validate_desc(desc, context):
        errors = []
        if 'mean' not in desc:
            errors.append(f"{context}: exponential distribution missing required field 'mean'")
        else:
            try:
                if float(desc['mean']) <= 0:
                    errors.append(f"{context}: exponential distribution 'mean' must be > 0, got {desc['mean']}")
            except (TypeError, ValueError):
                errors.append(f"{context}: exponential distribution 'mean' must be a number, got {desc['mean']!r}")
        return errors

class DistNormal:
    """
    Represents a normal (Gaussian) distribution with a given mean and standard deviation.
    """
    def __init__(self, mean, stddev):
        self.mean = mean
        self.stddev = stddev
    def __str__(self):
        return 'DistNormal(mean='+str(self.mean)+', stddev='+str(self.stddev)+')'
    def get_sample(self):
        """Return a normally distributed random value with the configured mean and stddev."""
        return np.random.normal(self.mean, self.stddev)

    @staticmethod
    def validate_desc(desc, context):
        errors = []
        if 'mean' not in desc:
            errors.append(f"{context}: normal distribution missing required field 'mean'")
        if 'stddev' not in desc:
            errors.append(f"{context}: normal distribution missing required field 'stddev'")
        else:
            try:
                if float(desc['stddev']) <= 0:
                    errors.append(f"{context}: normal distribution 'stddev' must be > 0, got {desc['stddev']}")
            except (TypeError, ValueError):
                errors.append(f"{context}: normal distribution 'stddev' must be a number, got {desc['stddev']!r}")
        return errors

class DistGMMTemporal:
    """
    Gaussian Mixture Model temporal distribution.
    Modulates an exponential interarrival time by time of day and day of week.
    Each day profile is an array of Gaussian components (utc_hour=μ, sigma=σ, weight).
    Days are keyed by ISO weekday (1=Mon, 7=Sun) with nearest-prior wraparound lookup.
    """
    def __init__(self, mean, days, clock):
        self.mean = mean
        self.days = days  # dict: str(day_number) -> list of {utc_hour, sigma, weight}
        self.clock = clock
        self.sorted_days = sorted(int(k) for k in self.days.keys())

    def __str__(self):
        return f'DistGMMTemporal(mean={self.mean}, days={list(self.days.keys())})'

    def _get_profile(self, day):
        # Walk back from the given ISO weekday to find the nearest defined day key.
        for i in range(7):
            candidate = (day - 1 - i) % 7 + 1
            if candidate in self.sorted_days:
                return self.days[str(candidate)]
        raise ValueError('No day profiles defined')

    def _get_multiplier(self, hour, profile):
        # Evaluate the sum of Gaussian components at the given fractional hour.
        # Handles midnight wraparound by checking offsets -24, 0, +24.
        total = 0.0
        for comp in profile:
            mu = comp['utc_hour']
            sigma = comp['sigma']
            w = comp['weight']
            best = 0.0
            for offset in (-24, 0, 24):
                diff = hour - mu + offset
                val = w * math.exp(-0.5 * (diff / sigma) ** 2)
                if val > best:
                    best = val
            total += best
        return total

    def get_sample(self):
        """
        Return a time-modulated exponential sample based
        on current clock time and day of week.
        """
        now = self.clock.now()
        day = now.isoweekday()
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0
        profile = self._get_profile(day)
        multiplier = self._get_multiplier(hour, profile)
        if multiplier <= 0:
            multiplier = 0.001
        return np.random.exponential(scale=self.mean / multiplier)

    @staticmethod
    def validate_desc(desc, context):
        errors = []
        if 'mean' not in desc:
            errors.append(f"{context}: gmm_temporal distribution missing required field 'mean'")
        else:
            try:
                if float(desc['mean']) <= 0:
                    errors.append(f"{context}: gmm_temporal distribution 'mean' must be > 0, got {desc['mean']}")
            except (TypeError, ValueError):
                errors.append(f"{context}: gmm_temporal distribution 'mean' must be a number, got {desc['mean']!r}")
        if 'days' not in desc or not desc['days']:
            errors.append(f"{context}: gmm_temporal distribution missing required field 'days' (must be a non-empty object)")
        else:
            days = desc['days']
            for key, components in days.items():
                try:
                    day_num = int(key)
                    if day_num < 1 or day_num > 7:
                        errors.append(f"{context}: gmm_temporal day key '{key}' must be an integer 1–7 (ISO weekday)")
                except (ValueError, TypeError):
                    errors.append(f"{context}: gmm_temporal day key '{key}' must be an integer 1–7 (ISO weekday)")
                if not components or not isinstance(components, list):
                    errors.append(f"{context}: gmm_temporal day '{key}' must be a non-empty list of components")
                else:
                    for j, comp in enumerate(components):
                        for field in ('utc_hour', 'sigma', 'weight'):
                            if field not in comp:
                                errors.append(f"{context}: gmm_temporal day '{key}' component [{j}] missing required field '{field}'")
        return errors

class Schedule:
    """
    A capacity schedule that returns a multiplier (0–1) for the current time.
    Used with --schedule to modulate max_entities over time.
    Supports 'constant' (flat capacity) and 'gmm_temporal' (time-varying) distributions.
    """
    def __init__(self, dist_config, clock):
        self.clock = clock
        dist_type = dist_config['type'].lower()
        if dist_type == 'constant':
            self._constant = float(dist_config['value'])
            self._gmm = None
        elif dist_type == 'gmm_temporal':
            days = dist_config.get('days')
            if not days:
                raise ValueError('Schedule gmm_temporal requires "days"')
            self._gmm = DistGMMTemporal(1.0, days, clock)
            self._constant = None
        else:
            raise ValueError(f'Schedule does not support distribution type "{dist_type}"')

    def get_multiplier(self):
        """Return the current capacity multiplier (0–1)."""
        if self._gmm is None:
            return self._constant
        now = self.clock.now()
        day = now.isoweekday()
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0
        profile = self._gmm._get_profile(day)
        return max(0.0, self._gmm._get_multiplier(hour, profile))


def parse_schedule(desc, clock):
    """Parse a schedule configuration and return a Schedule object."""
    return Schedule(desc, clock)


def parse_distribution(desc, clock=None):
    """
    Parse a distribution configuration and return a distribution object.

    Args:
        desc (dict): A dictionary describing the distribution configuration.
        clock: Optional Clock instance, required for temporal distribution types.

    Returns:
        Distribution: An object representing the parsed distribution.

    Raises:
        Exception: If the distribution configuration is invalid.
    """
    dist_type = desc['type'].lower()
    if dist_type == 'constant':
        return DistConstant(desc['value'])
    elif dist_type == 'uniform':
        return DistUniform(desc['min'], desc['max'])
    elif dist_type == 'exponential':
        return DistExponential(desc['mean'])
    elif dist_type == 'normal':
        return DistNormal(desc['mean'], desc['stddev'])
    elif dist_type == 'gmm_temporal':
        if clock is None:
            raise ValueError('Error: gmm_temporal distribution requires a clock')
        days = desc.get('days')
        if not days:
            raise ValueError('Error: gmm_temporal distribution requires at least one day profile in "days"')
        for key, components in days.items():
            day_num = int(key)
            if day_num < 1 or day_num > 7:
                raise ValueError(f'Error: gmm_temporal day key "{key}" must be 1-7 (ISO weekday)')
            if not components or not isinstance(components, list):
                raise ValueError(f'Error: gmm_temporal day "{key}" must be a non-empty array of components')
            for comp in components:
                for field in ('utc_hour', 'sigma', 'weight'):
                    if field not in comp:
                        raise ValueError(f'Error: gmm_temporal component missing required field "{field}"')
        return DistGMMTemporal(desc['mean'], days, clock)
    else:
        raise ValueError(f'Error: Unknown distribution "{dist_type}"')

KNOWN_DISTRIBUTION_TYPES = ('constant', 'uniform', 'exponential', 'normal', 'gmm_temporal')

def validate_distribution_desc(desc, context):
    """
    Validate a distribution config dict without constructing any objects.
    Returns a list of error strings.
    """
    errors = []
    if not isinstance(desc, dict):
        errors.append(f"{context}: distribution must be a JSON object, got {type(desc).__name__}")
        return errors
    if 'type' not in desc:
        errors.append(f"{context}: distribution missing required field 'type'")
        return errors
    dist_type = str(desc['type']).lower()
    if dist_type == 'constant':
        errors += DistConstant.validate_desc(desc, context)
    elif dist_type == 'uniform':
        errors += DistUniform.validate_desc(desc, context)
    elif dist_type == 'exponential':
        errors += DistExponential.validate_desc(desc, context)
    elif dist_type == 'normal':
        errors += DistNormal.validate_desc(desc, context)
    elif dist_type == 'gmm_temporal':
        errors += DistGMMTemporal.validate_desc(desc, context)
    else:
        errors.append(f"{context}: unknown distribution type '{desc['type']}' (known: {', '.join(KNOWN_DISTRIBUTION_TYPES)})")
    return errors


def parse_timestamp_distribution(desc):
    """
    Parse a timestamp distribution configuration and return a distribution object.

    Args:
        desc (dict): A dictionary describing the timestamp distribution configuration.

    Returns:
        Distribution: An object representing the parsed timestamp distribution.

    Raises:
        Exception: If the timestamp distribution configuration is invalid.
    """
    dist_type = desc['type'].lower()
    if dist_type == 'constant':
        value = dateutil.parser.isoparse(desc['value']).timestamp()
        return DistConstant(value)
    elif dist_type == 'uniform':
        min_value = dateutil.parser.isoparse(desc['min']).timestamp()
        max_value = dateutil.parser.isoparse(desc['max']).timestamp()
        return DistUniform(min_value, max_value)
    elif dist_type == 'exponential':
        mean = dateutil.parser.isoparse(desc['mean']).timestamp()
        return DistExponential(mean)
    elif dist_type == 'normal':
        mean = dateutil.parser.isoparse(desc['mean']).timestamp()
        stddev = desc['stddev']
        return DistNormal(mean, stddev)
    else:
        raise ValueError(f'Error: Unknown distribution "{dist_type}"')
