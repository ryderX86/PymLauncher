from enum import IntEnum


class Status(IntEnum):
    SUCCESS = 0
    INTERRUPTED = 1
    ERROR = 2
    ERROR_ZIPFILE = 3
    ERROR_FILE = 4
    ERROR_ARGS = 5
    ERROR_PROF = 6
