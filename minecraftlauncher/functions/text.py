"""
Helper functions for text stuff
"""

from string import digits, ascii_letters
import platform
import json
import re


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


def is_path_valid(fp: str):
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
