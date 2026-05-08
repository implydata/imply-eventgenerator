"""Dimension (field generator) classes for emitter records and state variables.

Each Dimension* class maps to a generator type in the config JSON
(e.g. DimensionGeneratorInt → "type": "int", DimensionGeneratorEnum → "type": "enum").

See docs/variables-generated.md for the config-level reference.
"""

import logging
import random
import string
import re
from datetime import datetime, timezone
from jinja2 import Environment, StrictUndefined
from ieg.distributions import parse_distribution, parse_timestamp_distribution, validate_distribution_desc

_dim_jinja_env = Environment(undefined=StrictUndefined)

logger = logging.getLogger('ieg')

#
# Classes for different types of emitter dimension
#

class DimensionGeneratorBase:
    """Base class for all dimension types. Handles cardinality, nulls, and missing."""

    def __init__(self, desc):
        self.name = desc['name']
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0

        if 'cardinality' not in desc.keys():
                raise Exception(f'Dimension {self.name} has no value for cardinality.')
        cardinality = desc['cardinality']

        if cardinality == 0:
            self.cardinality = None
            self.cardinality_distribution = None
        else:
            self.cardinality = []
            if 'cardinality_distribution' not in desc.keys():
                raise Exception(f'"{self.name}" dimension specifies a cardinality without a cardinality distribution.')
            self.cardinality_distribution = parse_distribution(desc['cardinality_distribution'])
            for i in range(cardinality):
                value = None
                while True:
                    value = self._get_raw_value()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)


    @staticmethod
    def validate_desc(desc, context):
        """Validate fields common to all DimensionGeneratorBase subclasses (int, float, ipaddress)."""
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'type' not in desc:
            logger.error("%s: missing required field 'type'", context)
            valid = False
        if 'cardinality' not in desc:
            logger.error("%s: missing required field 'cardinality'", context)
            valid = False
        else:
            cardinality = desc['cardinality']
            try:
                cardinality = int(cardinality)
                if cardinality < 0:
                    logger.error("%s: 'cardinality' must be an integer >= 0, got %s", context, desc['cardinality'])
                    valid = False
                elif cardinality > 0:
                    if 'cardinality_distribution' not in desc:
                        logger.error("%s: 'cardinality' > 0 requires 'cardinality_distribution'", context)
                        valid = False
                    else:
                        if not validate_distribution_desc(desc['cardinality_distribution'], f"{context} cardinality_distribution"):
                            valid = False
            except (TypeError, ValueError):
                logger.error("%s: 'cardinality' must be an integer, got %r", context, desc['cardinality'])
                valid = False
        if 'distribution' not in desc:
            logger.error("%s: missing required field 'distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['distribution'], f"{context} distribution"):
                valid = False
        return valid

    def _get_raw_value(self):
        """Generate a single raw value from the underlying distribution. Must be overridden by subclasses."""
        raise NotImplementedError("Unexpected error: Subclasses must implement _get_raw_value()")

    def get_stochastic_value(self):
        """Return a value, selecting from the cardinality pool if one was built, otherwise generating a fresh value."""
        if self.cardinality is not None:
            index = int(self.cardinality_distribution.get_sample())
            index = max(0, min(index, len(self.cardinality) - 1))
            return self.cardinality[index]
        return self._get_raw_value()

    def get_json_field_string(self):
        """
        Generate a JSON field string representation of the dimension.

        Returns:
            str: A JSON-formatted string representing the dimension's name and value.
                 If the value is null, the string will include "null".
        """
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                value = self.get_stochastic_value()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                value = self.cardinality[index]
            s = '"'+self.name+'":'+str(value)
        return s

    def is_missing(self):
        # Return True if the dimension value is missing.
        return random.random() < self.percent_missing

#
#  LONG dimensions
#

class DimensionGeneratorInt(DimensionGeneratorBase):
    """Generates integer values from a numeric distribution. Config type: "int"."""
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        super().__init__(desc)

    def __str__(self):
        return 'DimensionGeneratorInt(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    @staticmethod
    def validate_desc(desc, context):
        return DimensionGeneratorBase.validate_desc(desc, context)

    def _get_raw_value(self):
        return int(self.value_distribution.get_sample())

#
# FLOAT dimensions
#

class DimensionGeneratorFloat(DimensionGeneratorBase):
    """Generates float values from a numeric distribution with optional decimal precision. Config type: "float"."""
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        if 'precision' in desc:
            self.precision = desc['precision']
        else:
            self.precision = None
        super().__init__(desc)

    def __str__(self):
        return 'DimensionGeneratorFloat(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    @staticmethod
    def validate_desc(desc, context):
        valid = DimensionGeneratorBase.validate_desc(desc, context)
        if 'precision' in desc:
            try:
                p = int(desc['precision'])
                if p < 0:
                    logger.error("%s: 'precision' must be an integer >= 0, got %s", context, desc['precision'])
                    valid = False
            except (TypeError, ValueError):
                logger.error("%s: 'precision' must be an integer, got %r", context, desc['precision'])
                valid = False
        return valid

    def _get_raw_value(self):
        return float(self.value_distribution.get_sample())

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                value = self.get_stochastic_value()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                value = self.cardinality[index]
            if self.precision is None:
                s = '"'+self.name+'":'+str(value)
            else:
                format = '%.'+str(self.precision)+'f'
                s = '"'+self.name+'":'+str(format%value)
        return s

class DimensionGeneratorCounter:
    """Emits a sequentially incrementing integer. Config type: "counter".

    The counter is per-instance, not global — each DimensionGeneratorCounter object maintains
    its own sequence. Useful for surrogate keys within a single emitter.
    Fields: start (default 0), increment (default 1).
    """
    def __init__(self, desc):
        self.name = desc['name']
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0
        if 'start' in desc.keys():
            self.start = desc['start']
        else:
            self.start = 0
        if 'increment' in desc.keys():
            self.increment = desc['increment']
        else:
            self.increment = 1
        self.value = self.start
    def __str__(self):
        s = 'DimensionGeneratorCounter(name='+self.name
        if self.start != 0:
            s += ', '+str(self.start)
        if self.increment != 1:
            s += ', '+str(self.increment)
        s += ')'
        return s

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'start' in desc:
            try:
                float(desc['start'])
            except (TypeError, ValueError):
                logger.error("%s: 'start' must be numeric, got %r", context, desc['start'])
                valid = False
        if 'increment' in desc:
            try:
                float(desc['increment'])
            except (TypeError, ValueError):
                logger.error("%s: 'increment' must be numeric, got %r", context, desc['increment'])
                valid = False
        return valid

    def get_stochastic_value(self):
        v = self.value
        self.value += self.increment
        return v

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            s = '"'+self.name+'":"'+str(self.get_stochastic_value())+'"'
            return s

    def is_missing(self):
        return random.random() < self.percent_missing

#
# STRING dimensions
#

class DimensionStatic:
    """Always emits a fixed literal value. Config type: "static".

    value is any JSON scalar (str, int, float, bool); its type is inferred
    from the JSON value — no need to declare string:static vs int:static.
    Only valid in emitter dimensions, not in a state's variables block.
    """
    def __init__(self, desc):
        self.name = desc['name']
        self.value = desc['value']
        self.percent_missing = desc.get('percent_missing', 0) / 100.0

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'value' not in desc:
            logger.error("%s: missing required field 'value'", context)
            valid = False
        elif not isinstance(desc['value'], (str, int, float, bool)):
            logger.error("%s: 'value' must be a scalar (str, int, float, or bool), got %s", context, type(desc['value']).__name__)
            valid = False
        return valid

    def get_stochastic_value(self):
        return self.value

    def is_missing(self):
        return random.random() < self.percent_missing


class DimensionGeneratorString(DimensionGeneratorBase):
    """Generates random strings of a given length drawn from a character set. Config type: "string".

    length_distribution controls how many characters to generate per value.
    chars (optional) restricts the character set; defaults to all printable ASCII.
    """
    def __init__(self, desc):
        self.length_distribution = parse_distribution(desc['length_distribution'])
        if 'chars' in desc:
            self.chars = desc['chars']
        else:
            self.chars = string.printable
        super().__init__(desc)

    def __str__(self):
        return 'DimensionGeneratorString(name='+self.name+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+', chars='+self.chars+')'

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'cardinality' not in desc:
            logger.error("%s: missing required field 'cardinality'", context)
            valid = False
        else:
            try:
                cardinality = int(desc['cardinality'])
                if cardinality < 0:
                    logger.error("%s: 'cardinality' must be an integer >= 0, got %s", context, desc['cardinality'])
                    valid = False
                elif cardinality > 0:
                    if 'cardinality_distribution' not in desc:
                        logger.error("%s: 'cardinality' > 0 requires 'cardinality_distribution'", context)
                        valid = False
                    else:
                        if not validate_distribution_desc(desc['cardinality_distribution'], f"{context} cardinality_distribution"):
                            valid = False
            except (TypeError, ValueError):
                logger.error("%s: 'cardinality' must be an integer, got %r", context, desc['cardinality'])
                valid = False
        if 'length_distribution' not in desc:
            logger.error("%s: missing required field 'length_distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['length_distribution'], f"{context} length_distribution"):
                valid = False
        return valid

    def _get_raw_value(self):
        length = int(self.length_distribution.get_sample())
        return ''.join(random.choices(list(self.chars), k=length))

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                value = self.get_stochastic_value()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                value = self.cardinality[index]
            s = '"'+self.name+'":"'+str(value)+'"'
        return s

#
# TIMESTAMP dimensions
#

class DimensionGeneratorClock:
    """Captures the worker's current simulated clock time as a datetime. Config type: "clock".

    Used for the record timestamp and for start/end time capture in the
    setup → timer → emit pattern. Returns timezone-aware UTC datetimes.
    Unlike DimensionGeneratorTimestamp, this reflects the simulation clock, not a random range.
    """
    def __init__(self, clock, desc):
        self.clock = clock
        self.name = desc['name']  # Ensure self.name is set

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        return valid

    def get_stochastic_value(self):
        # Retrieve the current time from the Clock instance
        current_time = self.clock.now()
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)  # Default to UTC if no timezone
        return current_time

class DimensionGeneratorTimestamp(DimensionGeneratorBase):
    """Generates a random datetime within a fixed range, independent of the simulation clock. Config type: "timestamp".

    distribution min/max are ISO 8601 strings. Use DimensionGeneratorClock ("clock") instead
    when you want the record time to track the simulation clock.
    """
    def __init__(self, desc):
        self.name = desc['name']
        self.value_distribution = parse_timestamp_distribution(desc['distribution'])
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0
        cardinality = desc['cardinality']
        if cardinality == 0:
            self.cardinality = None
            self.cardinality_distribution = None
        else:
            if 'cardinality_distribution' not in desc.keys():
                raise Exception(f'"{self.name}" dimension specifies a cardinality without a cardinality distribution.')
            self.cardinality = []
            self.cardinality_distribution = parse_distribution(desc['cardinality_distribution'])
            for i in range(cardinality):
                value = None
                while True:
                    value = self._get_raw_value()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)

    def __str__(self):
        return 'DimensionGeneratorTimestamp(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'cardinality' not in desc:
            logger.error("%s: missing required field 'cardinality'", context)
            valid = False
        if 'distribution' not in desc:
            logger.error("%s: missing required field 'distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['distribution'], f"{context} distribution"):
                valid = False
        return valid

    def _get_raw_value(self):
        # Return a random timestamp as a datetime object
        timestamp = datetime.fromtimestamp(self.value_distribution.get_sample())
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)  # Default to UTC if no timezone
        return timestamp

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                value = self.get_stochastic_value()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                value = self.cardinality[index]
            s = '"'+self.name+'":"'+str(value)+'"'
        return s

    def is_missing(self):
        return random.random() < self.percent_missing

class DimensionGeneratorIPAddress(DimensionGeneratorBase):
    """Generates IPv4 addresses from a numeric distribution over the 32-bit address space. Config type: "ipaddress".

    distribution min/max are integers representing the packed 32-bit address.
    Use a CIDR range by computing min/max from the network prefix.
    """
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        super().__init__(desc)

    def __str__(self):
        return 'DimensionGeneratorIPAddress(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    @staticmethod
    def validate_desc(desc, context):
        return DimensionGeneratorBase.validate_desc(desc, context)

    def _get_raw_value(self):
        value = int(self.value_distribution.get_sample())
        return str((value & 0xFF000000) >> 24)+'.'+str((value & 0x00FF0000) >> 16)+'.'+str((value & 0x0000FF00) >> 8)+'.'+str(value & 0x000000FF)

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                value = self.get_stochastic_value()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                value = self.cardinality[index]
            s = '"'+self.name+'":"'+str(value)+'"'
        return s

#
# Complex dimensions
#

class DimensionGeneratorEnum:
    """Selects a value from a fixed list using a cardinality_distribution index. Config type: "enum".

    cardinality_distribution is used as a zero-based index into the values list, so
    uniform(min=0, max=N-1) gives equal probability. The index is clamped to
    [0, len(values)-1] to prevent out-of-range errors.
    """
    def __init__(self, desc):
        self.name = desc['name']
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0
        self.cardinality = desc['values']
        if 'cardinality_distribution' not in desc.keys():
            raise Exception(f'Dimension {self.name} specifies a cardinality without a cardinality distribution.')
        self.cardinality_distribution = parse_distribution(desc['cardinality_distribution'])

    def __str__(self):
        return 'DimensionGeneratorEnum(name='+self.name+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        values = desc.get('values')
        if not values or not isinstance(values, list):
            logger.error("%s: 'values' required and must be a non-empty list", context)
            valid = False
        if 'cardinality_distribution' not in desc:
            logger.error("%s: missing required field 'cardinality_distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['cardinality_distribution'], f"{context} cardinality_distribution"):
                valid = False
            cd = desc['cardinality_distribution']
            if isinstance(cd, dict) and cd.get('type', '').lower() == 'uniform' and values and isinstance(values, list):
                try:
                    if int(cd.get('max', 0)) > len(values) - 1:
                        logger.warning("%s: cardinality_distribution uniform 'max' (%s) exceeds last valid index (%d) — distribution will be skewed", context, cd['max'], len(values) - 1)
                        # do NOT set valid = False — this is non-fatal
                except (TypeError, ValueError):
                    pass
        return valid

    def get_stochastic_value(self):
        index = int(self.cardinality_distribution.get_sample())
        if index < 0:
            index = 0
        if index >= len(self.cardinality):
            index = len(self.cardinality)-1
        return self.cardinality[index]

    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            s = '"'+self.name+'":"'+str(self.get_stochastic_value())+'"'
        return s

    def is_missing(self):
        return random.random() < self.percent_missing

class DimensionGeneratorObject():
    """Generates a nested JSON object from a list of child dimensions. Config type: "object"."""
    def __init__(self, clock, desc):
        self.global_clock = clock
        self.name = desc['name']
        self.dimensions = get_variables(desc['dimensions'], self.global_clock)
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0
        cardinality = desc['cardinality']
        if cardinality == 0:
            self.cardinality = None
            self.cardinality_distribution = None
        else:
            self.cardinality = []
            if 'cardinality_distribution' not in desc.keys():
                raise Exception(f'Dimension {self.name} specifies a cardinality without a cardinality distribution.')
            self.cardinality_distribution = parse_distribution(desc['cardinality_distribution'])
            for i in range(cardinality):
                Value = None
                while True:
                    value = self.get_instance()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)

    def __str__(self):
        s = 'DimensionGeneratorObject(name='+self.name+', dimensions=['
        for e in self.dimensions:
            s += ',' + str(e)
        s += '])'
        return s

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'cardinality' not in desc:
            logger.error("%s: missing required field 'cardinality'", context)
            valid = False
        else:
            try:
                cardinality = int(desc['cardinality'])
                if cardinality < 0:
                    logger.error("%s: 'cardinality' must be an integer >= 0, got %s", context, desc['cardinality'])
                    valid = False
                elif cardinality > 0:
                    if 'cardinality_distribution' not in desc:
                        logger.error("%s: 'cardinality' > 0 requires 'cardinality_distribution'", context)
                        valid = False
                    else:
                        if not validate_distribution_desc(desc['cardinality_distribution'], f"{context} cardinality_distribution"):
                            valid = False
            except (TypeError, ValueError):
                logger.error("%s: 'cardinality' must be an integer, got %r", context, desc['cardinality'])
                valid = False
        dims = desc.get('dimensions')
        if not dims or not isinstance(dims, list):
            logger.error("%s: 'dimensions' required and must be a non-empty list", context)
            valid = False
        else:
            for nested in dims:
                if not validate_dimension_desc(nested, f"{context}, nested dimension '{nested.get('name', '?')}'"):
                    valid = False
        return valid

    def get_instance(self):
        s = '"'+self.name+'": {'
        for e in self.dimensions:
            s += e.get_json_field_string() + ','
        s = s[:-1] +  '}'
        return s


    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                s = self.get_instance()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                s = self.cardinality[index]
        return s

    def is_missing(self):
        return random.random() < self.percent_missing

class DimensionGeneratorList():
    """Generates a JSON array whose length and element type are both drawn from distributions. Config type: "list".

    length_distribution controls the number of elements per array.
    selection_distribution indexes into the elements list to pick the element type for each slot.
    """
    def __init__(self, clock, desc):
        self.global_clock = clock
        self.name = desc['name']
        self.elements = get_variables(desc['elements'], self.global_clock)
        self.length_distribution = parse_distribution(desc['length_distribution'])
        self.selection_distribution = parse_distribution(desc['selection_distribution'])
        if 'percent_nulls' in desc.keys():
            self.percent_nulls = desc['percent_nulls'] / 100.0
        else:
            self.percent_nulls = 0.0
        if 'percent_missing' in desc.keys():
            self.percent_missing = desc['percent_missing'] / 100.0
        else:
            self.percent_missing = 0.0
        cardinality = desc['cardinality']
        if cardinality == 0:
            self.cardinality = None
            self.cardinality_distribution = None
        else:
            self.cardinality = []
            if 'cardinality_distribution' not in desc.keys():
                raise Exception(f'Dimension {self.name} specifies a cardinality without a cardinality distribution.')
            self.cardinality_distribution = parse_distribution(desc['cardinality_distribution'])
            for i in range(cardinality):
                Value = None
                while True:
                    value = self.get_instance()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)

    def __str__(self):
        s = 'DimensionGeneratorObject(name='+self.name
        s += ', length_distribution='+str(self.length_distribution)
        s += ', selection_distribution='+str(self.selection_distribution)
        s += ', elements=['
        for e in self.elements:
            s += ',' + str(e)
        s += '])'
        return s

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'cardinality' not in desc:
            logger.error("%s: missing required field 'cardinality'", context)
            valid = False
        else:
            try:
                cardinality = int(desc['cardinality'])
                if cardinality < 0:
                    logger.error("%s: 'cardinality' must be an integer >= 0, got %s", context, desc['cardinality'])
                    valid = False
                elif cardinality > 0:
                    if 'cardinality_distribution' not in desc:
                        logger.error("%s: 'cardinality' > 0 requires 'cardinality_distribution'", context)
                        valid = False
                    else:
                        if not validate_distribution_desc(desc['cardinality_distribution'], f"{context} cardinality_distribution"):
                            valid = False
            except (TypeError, ValueError):
                logger.error("%s: 'cardinality' must be an integer, got %r", context, desc['cardinality'])
                valid = False
        elems = desc.get('elements')
        if not elems or not isinstance(elems, list):
            logger.error("%s: 'elements' required and must be a non-empty list", context)
            valid = False
        else:
            for elem in elems:
                if not validate_dimension_desc(elem, f"{context}, element '{elem.get('name', '?')}'"):
                    valid = False
        if 'length_distribution' not in desc:
            logger.error("%s: missing required field 'length_distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['length_distribution'], f"{context} length_distribution"):
                valid = False
        if 'selection_distribution' not in desc:
            logger.error("%s: missing required field 'selection_distribution'", context)
            valid = False
        else:
            if not validate_distribution_desc(desc['selection_distribution'], f"{context} selection_distribution"):
                valid = False
        return valid

    def get_instance(self):
        s = '"'+self.name+'": ['
        length = int(self.length_distribution.get_sample())
        for i in range(length):
            index = int(self.selection_distribution.get_sample())
            if index < 0:
                index = 0
            if index >= length:
                index = length-1
            s += re.sub('^.*?:', '', self.elements[index].get_json_field_string(), count=1) + ','
        s = s[:-1] +  ']'
        return s


    def get_json_field_string(self):
        if random.random() < self.percent_nulls:
            s = '"'+self.name+'": null'
        else:
            if self.cardinality is None:
                s = self.get_instance()
            else:
                index = int(self.cardinality_distribution.get_sample())
                if index < 0:
                    index = 0
                if index >= len(self.cardinality):
                    index = len(self.cardinality)-1
                s = self.cardinality[index]
        return s

    def is_missing(self):
        return random.random() < self.percent_missing


#
# Classes for handling variables
#

class DimensionVariable:
    """Outputs the current value of a named worker variable. Config type: "variable".

    Variable values are set by activity states and persist for the lifetime of the worker.
    If the referenced variable has not been set by the time the emitter runs, a KeyError
    will be raised at runtime. Use validate_config() to catch this pre-flight.
    Only valid in emitter dimensions, not in a state's variables block.
    """
    def __init__(self, desc):
        self.name = desc['name']
        self.variable_name = desc['variable']

    def __str__(self):
        return 'DimensionVariable(name='+self.name+', value='+self.variable_name+')'

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'variable' not in desc:
            logger.error("%s: missing required field 'variable'", context)
            valid = False
        return valid

    def get_json_field_string(self, variables): # NOTE: because of timing, this method has a different signature than the other elements
        value = variables[self.variable_name]
        return '"'+self.name+'":"'+str(value)+'"'


class DimensionVariableTemplate:
    """Composes multiple namespace variables into a single string via a Jinja2 template.
    Config type: "variable:template". Valid in both emitter dimensions and variables blocks.

    The template is rendered against the full variable namespace at render time.
    Any namespace key can be referenced directly: {{ var_category }}, {{ var_product }}, etc.
    Raises jinja2.UndefinedError if a referenced variable is not in the namespace.
    When used in a variables block, earlier variables in the same block are already visible.
    """
    def __init__(self, desc):
        self.name = desc['name']
        self.template = _dim_jinja_env.from_string(desc['template'])

    def __str__(self):
        return f'DimensionVariableTemplate(name={self.name})'

    @staticmethod
    def validate_desc(desc, context):
        valid = True
        if 'name' not in desc:
            logger.error("%s: missing required field 'name'", context)
            valid = False
        if 'template' not in desc:
            logger.error("%s: missing required field 'template'", context)
            valid = False
        return valid

    def evaluate(self, namespace):
        return self.template.render(**namespace)

    def get_json_field_string(self, variables):
        value = self.template.render(**variables)
        return '"' + self.name + '":"' + str(value) + '"'


#
# Configuration parsing functions
#

_GENERATOR_FACTORIES = {
    'generator:counter':   lambda desc, clock: DimensionGeneratorCounter(desc),
    'generator:enum':      lambda desc, clock: DimensionGeneratorEnum(desc),
    'generator:string':    lambda desc, clock: DimensionGeneratorString(desc),
    'generator:int':       lambda desc, clock: DimensionGeneratorInt(desc),
    'generator:float':     lambda desc, clock: DimensionGeneratorFloat(desc),
    'generator:timestamp': lambda desc, clock: DimensionGeneratorTimestamp(desc),
    'generator:clock':     lambda desc, clock: DimensionGeneratorClock(clock, desc),
    'generator:ipaddress': lambda desc, clock: DimensionGeneratorIPAddress(desc),
    'generator:object':    lambda desc, clock: DimensionGeneratorObject(clock, desc),
    'generator:list':      lambda desc, clock: DimensionGeneratorList(clock, desc),
}

_GENERATOR_VALIDATORS = {
    'generator:counter':   DimensionGeneratorCounter,
    'generator:enum':      DimensionGeneratorEnum,
    'generator:string':    DimensionGeneratorString,
    'generator:int':       DimensionGeneratorInt,
    'generator:float':     DimensionGeneratorFloat,
    'generator:timestamp': DimensionGeneratorTimestamp,
    'generator:clock':     DimensionGeneratorClock,
    'generator:ipaddress': DimensionGeneratorIPAddress,
    'generator:object':    DimensionGeneratorObject,
    'generator:list':      DimensionGeneratorList,
}

def parse_element(desc, global_clock):
    t = desc['type'].lower()
    if t == 'static':
        return DimensionStatic(desc)
    elif t == 'variable':
        return DimensionVariable(desc)
    elif t == 'variable:template':
        return DimensionVariableTemplate(desc)
    elif t in _GENERATOR_FACTORIES:
        return _GENERATOR_FACTORIES[t](desc, global_clock)
    else:
        raise Exception(f'Error: Unknown dimension type "{desc["type"]}"')

def get_variables(desc, global_clock):
    # Parses the emitter configuration and returns a list of dimension objects using parse_element().
    elements = []
    for element in desc:
        elements.append(parse_element(element, global_clock))  # Pass global_clock
    return elements

def get_dimensions(desc, global_clock):
    # Parses the emitter configuration and returns a list of dimension objects using parse_element().
    elements = get_variables(desc, global_clock)  # Pass global_clock
    return elements

KNOWN_DIMENSION_TYPES = ('static', 'variable', 'variable:template') + tuple(sorted(_GENERATOR_FACTORIES))

def validate_dimension_desc(desc, context):
    """
    Validate a dimension config dict without constructing any objects.
    Logs errors/warnings directly and returns True (valid) or False (invalid).
    """
    if not isinstance(desc, dict):
        logger.error("%s: dimension must be a JSON object, got %s", context, type(desc).__name__)
        return False
    if 'type' not in desc:
        logger.error("%s: missing required field 'type'", context)
        return False
    dim_type = str(desc['type']).lower()
    if dim_type == 'static':
        return DimensionStatic.validate_desc(desc, context)
    elif dim_type == 'variable':
        return DimensionVariable.validate_desc(desc, context)
    elif dim_type == 'variable:template':
        return DimensionVariableTemplate.validate_desc(desc, context)
    elif dim_type in _GENERATOR_VALIDATORS:
        return _GENERATOR_VALIDATORS[dim_type].validate_desc(desc, context)
    else:
        logger.error(
            "%s: unknown dimension type '%s' (known: %s)",
            context, desc['type'], ', '.join(KNOWN_DIMENSION_TYPES)
        )
        return False
