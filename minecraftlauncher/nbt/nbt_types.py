from enum import IntEnum

class NBTTypeTable(IntEnum):
    TAG_END = 0x00
    TAG_BYTE = 0x01
    TAG_SHORT = 0x02
    TAG_INT  = 0x03
    TAG_LONG = 0x04
    TAG_FLOAT = 0x05
    TAG_DOUBLE = 0x06
    TAG_BYTE_ARRAY = 0x07
    TAG_STRING = 0x08
    TAG_LIST = 0x09
    TAG_COMPOUND = 0x0A
    TAG_INT_ARRAY = 0x0B
    TAG_LONG_ARRAY = 0x0C