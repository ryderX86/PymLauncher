"""
Helper functions for text stuff
"""

import json


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
