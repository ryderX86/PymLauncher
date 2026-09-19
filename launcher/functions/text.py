"""
Helper functions for text stuff
"""

from string import ascii_letters, digits
import json
import os
import platform
import re

from launcher import constants


def indent(text: str | dict | list, amount: int = 2):
    """Indents all lines of a `str` with `amount:int` (default: `2`) spaces."""

    match text:
        case dict():
            text = json.dumps(text, indent=amount)
        case list():
            text = ", ".join(text)
        case str():
            pass
        case _:
            raise TypeError(type(text).__name__)

    lines = text.split("\n")

    for i, line in enumerate(lines):
        line = (" " * amount) + line
        lines[i] = line  # type: ignore

    return "\n".join(lines)


def truncate(
    text: str,
    max_length: int,
    placeholder: str = "...",
) -> str:
    if len(text) > max_length:
        text = "".join((text[: max_length + 1], placeholder))
    return text


_WIN_PATH_REGEX = (
    r"(([A-Za-z]:\\)|(%[a-zA-Z0-9]+%\\?))(((?!(\.\.)|(CON)|(PRN)|(AUX)|(NUL)|("
    r"COM[0-9¹²³])|(LPT[0-9¹²³])|([^\\]+\.[\\\.])|([<>:\"/?*\x00-\x1f\\]))[^<>"
    r":\"/?*\x00-\x1f\\]*)\\?)+"
)
_POSIX_PATH_REGEX = r"((~/|/)((?![^/]+\.)[^\x00\n\r\/]+/?)+)|~"

match platform.system():
    case "Windows":
        FP_REGEX = _WIN_PATH_REGEX
    case _:
        FP_REGEX = _POSIX_PATH_REGEX


def is_path_valid(fp: str | os.PathLike):
    if not isinstance(fp, str):
        fp = str(fp)
    if platform.system() == "Windows":
        fp = fp.replace("/", "\\")
    m = re.match(FP_REGEX, fp)
    if not m:
        return False
    return m.string == fp


_PATHSAFE_ALLOWED_CHARS = "".join((".-_", ascii_letters, digits))


def pathsafe_str(text: str) -> str:
    output = []
    for char in text:
        if char not in _PATHSAFE_ALLOWED_CHARS:
            continue
        output.append(char)
    return "".join(output)


match constants.OS:
    case "windows":
        BYTE_SIZE = 1024
    case "osx":
        BYTE_SIZE = 1000
    case "linux":
        BYTE_SIZE = 1024
    case _:
        BYTE_SIZE = 1000

match constants.OS:
    case "linux":
        KB = "KiB"
        KB_L = "kibibytes"
        MB = "MiB"
        MB_L = "mebibytes"
        GB = "GiB"
        GB_L = "gibibytes"
    case _:
        KB = "KB"
        KB_L = "kilobytes"
        MB = "MB"
        MB_L = "megabytes"
        GB = "GB"
        GB_L = "gigabytes"


def display_file_size(base_size: int, long: bool = False):
    size: int | float = base_size
    if long:
        current_display = "bytes"
        kb = KB_L
        mb = MB_L
        gb = GB_L
    else:
        current_display = "B"
        kb = KB
        mb = MB
        gb = GB
    # byte->kilobyte
    if size > BYTE_SIZE:
        current_display = kb
        size /= BYTE_SIZE
    # kilo->mega
    if size > BYTE_SIZE:
        current_display = mb
        size /= BYTE_SIZE
    # mega->giga
    if size > BYTE_SIZE:
        current_display = gb
        size /= BYTE_SIZE

    # trim decimal
    size_s_raw = str(size)
    size_s_split = size_s_raw.split(".")
    if len(size_s_split) > 1:
        size_s = ".".join((size_s_split[0], size_s_split[1][:2]))
    else:
        size_s = size_s_raw

    if long:
        return " ".join((size_s, current_display))
    else:
        return "".join((size_s, current_display))
