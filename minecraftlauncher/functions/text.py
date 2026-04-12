"""
Helper functions for text stuff
"""

def indent(text:str, amount:int=2):
    """Indents all lines of a `str` with `amount:int` (default: `2`) spaces."""

    lines = text.split("\n")
    
    # doing it this way so replacing it is permanent
    for i in range(len(lines)):
        line = lines[i]
        line = (" " * amount) + line
        lines[i] = line

    return '\n'.join(lines)