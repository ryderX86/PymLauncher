import logging

log = logging.getLogger(__name__)


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    r = int(h[0:2], 16) / 255
    g = int(h[2:4], 16) / 255
    b = int(h[4:], 16) / 255
    return r, g, b


def hex_to_rgbi(h: str):
    h = h.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:], 16)
    return r, g, b


def rgb_to_hex(r, g, b):
    r = int(r * 255)
    g = int(g * 255)
    b = int(b * 255)
    return f"{hex(r)[2:]}{hex(g)[2:]}{hex(b)[2:]}"
