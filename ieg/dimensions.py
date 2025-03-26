import random
import string
import re
from datetime import datetime
from ieg.distributions import parse_distribution, parse_timestamp_distribution

#
# Classes for different types of emitter dimension
#

class DimensionBase:
    """
    Base class for defining emitter dimensions.

    This class provides common functionality for handling dimension attributes such as
    cardinality, null percentage, and missing percentage. It also defines methods for
    generating stochastic values and JSON field strings, which are intended to be
    overridden by subclasses.
    """

    def __init__(self, desc):
        """
        Initialize the base dimension with the given description.

        Args:
            desc (dict): A dictionary containing the dimension configuration. It must
                         include the 'name' and 'cardinality' keys, and optionally
                         'percent_nulls', 'percent_missing', and 'cardinality_distribution'.

        Raises:
            Exception: If 'cardinality' or 'cardinality_distribution' is missing when required.
        """
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
                    value = self.get_stochastic_value()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)


    def get_stochastic_value(self):
        """
        Generate a random individual value for the dimension.

        This method is intended to be overridden by subclasses to provide specific
        stochastic value generation logic.
        """
        pass

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

class DimensionInt(DimensionBase):
    # Represents an integer dimension.
    # Generates random integers based on a value distribution.
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        super().__init__(desc)

    def __str__(self):
        return 'DimensionInt(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    def get_stochastic_value(self):
        return int(self.value_distribution.get_sample())

#
# FLOAT dimensions
#

class DimensionFloat(DimensionBase):
    # Represents a float dimension.
    # Generates random float values based on a value distribution and optional precision.
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        if 'precision' in desc:
            self.precision = desc['precision']
        else:
            self.precision = None
        super().__init__(desc)

    def __str__(self):
        return 'DimensionFloat(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    def get_stochastic_value(self):
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
    
class DimensionCounter:
    # Represents a counter dimension.
    # Generates sequential values starting from a specified value.
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
        s = 'DimensionCounter(name='+self.name
        if self.start != 0:
            s += ', '+str(self.start)
        if self.increment != 1:
            s += ', '+str(self.increment)
        s += ')'
        return s

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

class DimensionString(DimensionBase):
    # Generates random strings based on a length distribution and character set.
    def __init__(self, desc):
        self.length_distribution = parse_distribution(desc['length_distribution'])
        if 'chars' in desc:
            self.chars = desc['chars']
        else:
            self.chars = string.printable
        super().__init__(desc)

    def __str__(self):
        return 'DimensionString(name='+self.name+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+', chars='+self.chars+')'

    def get_stochastic_value(self):
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

class DimensionStringTime:
    # Generates the current timestamp in ISO format.
    def __init__(self, global_clock):
        self.global_clock = global_clock
        self.name = "time"  # Add a default name attribute

    def __str__(self):
        return 'DimensionStringTime()'

    def get_json_field_string(self):
        now = self.global_clock.now().isoformat()[:-3]
        return '"time":"' + now + '"'

    def get_stochastic_value(self):
        # Return the current time value
        return self.global_clock.now().isoformat()[:-3]

class DimensionStringTimestamp(DimensionBase):
    # Generates random timestamps based on a distribution.
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
                Value = None
                while True:
                    value = self.get_stochastic_value()
                    if value not in self.cardinality:
                        break
                self.cardinality.append(value)

    def __str__(self):
        return 'DimensionStringTimestamp(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    def get_stochastic_value(self):
        return datetime.fromtimestamp(self.value_distribution.get_sample()).isoformat()[:-3]

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

class DimensionIPAddress(DimensionBase):
    # Generates random IP addresses based on a value distribution.
    def __init__(self, desc):
        self.value_distribution = parse_distribution(desc['distribution'])
        super().__init__(desc)

    def __str__(self):
        return 'DimensionIPAddress(name='+self.name+', value_distribution='+str(self.value_distribution)+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

    def get_stochastic_value(self):
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

class DimensionEnum:
   # Return a value selected from a list.
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
        return 'DimensionEnum(name='+self.name+', cardinality='+str(self.cardinality)+', cardinality_distribution='+str(self.cardinality_distribution)+')'

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

class DimensionObject():

    # Generates JSON objects with nested dimensions.

    def __init__(self, desc):
        self.name = desc['name']
        self.dimensions = get_variables(desc['dimensions'])
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
        s = 'DimensionObject(name='+self.name+', dimensions=['
        for e in self.dimensions:
            s += ',' + str(e)
        s += '])'
        return s

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

class DimensionList():

    # Generates lists of elements based on length and selection distributions.

    def __init__(self, desc):
        self.name = desc['name']
        self.elements = get_variables(desc['elements'])
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
        s = 'DimensionObject(name='+self.name
        s += ', length_distribution='+str(self.length_distribution)
        s += ', selection_distribution='+str(self.selection_distribution)
        s += ', elements=['
        for e in self.elements:
            s += ',' + str(e)
        s += '])'
        return s

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
    # Generate values based on a variable defined in the state machine.
    def __init__(self, desc):
        self.name = desc['name']
        self.variable_name = desc['variable']

    def __str__(self):
        return 'DimensionVariable(name='+self.name+', value='+self.variable_name+')'

    def get_json_field_string(self, variables): # NOTE: because of timing, this method has a different signature than the other elements
        value = variables[self.variable_name]
        return '"'+self.name+'":"'+str(value)+'"'

# 
# Configuration parsing functions
#

def parse_element(desc):
    # Parses a given dimension configuration and returns the corresponding dimension object.

    if desc['type'].lower() == 'counter':
        el = DimensionCounter(desc)
    elif desc['type'].lower() == 'enum':
        el = DimensionEnum(desc)
    elif desc['type'].lower() == 'string':
        el = DimensionString(desc)
    elif desc['type'].lower() == 'int':
        el = DimensionInt(desc)
    elif desc['type'].lower() == 'float':
        el = DimensionFloat(desc)
    elif desc['type'].lower() == 'timestamp':
        el = DimensionStringTimestamp(desc)
    elif desc['type'].lower() == 'ipaddress':
        el = DimensionIPAddress(desc)
    elif desc['type'].lower() == 'variable':
        el = DimensionVariable(desc)
    elif desc['type'].lower() == 'object':
        el = DimensionObject(desc)
    elif desc['type'].lower() == 'list':
        el = DimensionList(desc)
    else:
        msg = 'Error: Unknown dimension type "'+desc['type']+'"'
        raise Exception(msg)
    return el

def get_variables(desc):
    # Parses the emitter configuration and returns a list of dimension objects using parse_element().
    elements = []
    for element in desc:
        el = parse_element(element)
        elements.append(el)
    return elements

def get_dimensions(desc, global_clock):
    # Parses the emitter configuration and returns a list of dimension objects using parse_element().
    elements = get_variables(desc)
    elements.insert(0, DimensionStringTime(global_clock))
    return elements
