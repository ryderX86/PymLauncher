from enum import IntEnum
from typing import Callable, Any
import json
import logging
import string

log = logging.getLogger(__name__)

def match_chars(func:Callable[[Any], bool], obj:str):
    """
    Filters either a string by `func` (must take 1 arg and return a `bool`).
    """
    match list:
        case str():
            STRING_MODE = True
        case list():
            STRING_MODE = False
    
    for char in obj:
        if not func(char):
            return False
    return True

class OptionsTxt:
    """
    Hacky class for handling an options.txt file from a profile import/export.
    """
    class ValueType(IntEnum):
        UNKNOWN = 0
        BOOL = 1
        INTEGER = 2
        FLOAT = 3
        STRING = 4
        ENUM = 5
        STRING_LIST = 6
        KEYBIND = 7
        LONG_FLOAT = 8

    alpha_lower = "abcdefghijklmnopqrstuvwxyz"
    alpha_upper = alpha_lower.upper()
    enum_test = lambda s, v, t=alpha_upper: v in t
    alpha = alpha_lower + alpha_upper
    numeric = "0123456789"
    float_ = numeric + "."
    string_ = alpha + numeric + "_\\/."
    keyboard_test = lambda s, v: v.startswith("key.keyboard.")
    mouse_test = lambda s, v: v.startswith("key.mouse.")
    bool_test = lambda s, v: v in ("true", "false")
    true = lambda s, v: v == "true"
    false = lambda s, v: v == "false"
    list_test = lambda s, v: v.startswith("[") and v.endswith("]")
    def __init__(self, options:str):
        option_lines = options.split("\n")
        options_dict = {}
        for line in option_lines:
            keyval = line.split(":")
            if len(keyval) > 2:
                log.warning("Multiple colons in options.txt line: \"%s\""
                            % line)
                keyval = [keyval[0], ":".join(keyval[1:])]
                log.debug("Parsing line as {\"%s\": \"%s\"}"
                          % keyval[0], keyval[1])
            key = keyval[0]
            val = keyval[1]

            get_test = lambda t: lambda v, i=t: v in i
            
            # determine type
            t = self.ValueType.UNKNOWN

            if self.enum_test(val):
                t = self.ValueType.ENUM
            elif match_chars(get_test(self.alpha_lower + "\""), val):
                t = self.ValueType.ENUM
            elif self.keyboard_test(val):
                t = self.ValueType.KEYBIND
            elif self.mouse_test(val):
                t = self.ValueType.KEYBIND
            elif match_chars(get_test(self.string_), val):
                t = self.ValueType.STRING
            if match_chars(get_test(self.numeric), val):
                t = self.ValueType.INTEGER
            elif match_chars(get_test(self.float_), val):
                if len(val) > 20:
                    log.warning("long float in options.txt @ '%s'" % key)
                    t = self.ValueType.LONG_FLOAT
                else:
                    t = self.ValueType.FLOAT
            if self.bool_test(val):
                t = self.ValueType.BOOL
            
            if t == self.ValueType.UNKNOWN:
                log.warning("Couldn't determine options.txt value type for "
                            "'%s', proceeded as a string.")
            
            