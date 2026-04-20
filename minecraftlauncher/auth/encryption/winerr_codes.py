from enum import IntEnum

class WinErrorCode(IntEnum):
    ERROR_INVALID_DATA = 13
    ERROR_OUTOFMEMORY = 14
    ERROR_CRC = 23 # Cyclic redundancy check
    ERROR_BAD_LENGTH = 24 # wrong amount of arguments(?)