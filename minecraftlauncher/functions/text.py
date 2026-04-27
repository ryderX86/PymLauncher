"""
Helper functions for text stuff
"""

import json


def indent(text: str | dict | list, amount: int = 2):
    """Indents all lines of a `str` with `amount:int` (default: `2`) spaces."""

    if isinstance(text, dict):
        text = json.dumps(text, indent=amount)
    elif isinstance(text, list):
        text = ", ".join(text)
    elif isinstance(text, str):
        pass
    else:
        raise TypeError(type(text).__name__)

    lines = text.split("\n")

    # doing it this way so replacing it is permanent
    for i, line in enumerate(lines):
        line = (" " * amount) + line
        lines[i] = line  # type: ignore

    return "\n".join(lines)
