"""
This module provides utilities for parsing and handling distributions.

Distributions are used to generate random values based on specified probability
distributions. This module includes functions for parsing distribution configurations
and generating samples from them.
"""

import numpy as np
import dateutil.parser
from datetime import datetime

class DistConstant:
    # Represents a constant value distribution.
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return 'DistConstant(value='+str(self.value)+')'
    def get_sample(self):
        return self.value

class DistUniform:
    # Represents a uniform distribution between a minimum and maximum value.
    def __init__(self, min_value, max_value):
        self.min_value = min_value
        self.max_value = max_value
    def __str__(self):
        return 'DistUniform(min_value='+str(self.min_value)+', max_value='+str(self.max_value)+')'
    def get_sample(self):
        return np.random.uniform(self.min_value, self.max_value+1)

class DistExponential:
    # Represents an exponential distribution with a given mean.
    def __init__(self, mean):
        self.mean = mean
    def __str__(self):
        return 'DistExponential(mean='+str(self.mean)+')'
    def get_sample(self):
        return np.random.exponential(scale=self.mean)

class DistNormal:
    # Represents a normal (Gaussian) distribution with a given mean and standard deviation.
    def __init__(self, mean, stddev):
        self.mean = mean
        self.stddev = stddev
    def __str__(self):
        return 'DistNormal(mean='+str(self.mean)+', stddev='+str(self.stddev)+')'
    def get_sample(self):
        return np.random.normal(self.mean, self.stddev)

def parse_distribution(desc):
    """
    Parse a distribution configuration and return a distribution object.

    Args:
        desc (dict): A dictionary describing the distribution configuration.

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
    else:
        raise ValueError(f'Error: Unknown distribution "{dist_type}"')

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
