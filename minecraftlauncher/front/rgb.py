import logging

log = logging.getLogger(__name__)
"""
def _rl(v:int|float):
    fv = min(v, 255)
    fv = int(max(fv, 0))
    if fv != v:
        log.warning("filter %d -> %d" % (v, fv))
    return fv

def _sl(v:int|float):
    fv = min(v, 255)
    return int(max(fv, 0))

class RGB:
    @singledispatch
    def __init__(self, r:int, g:int, b:int):
        self._rv(r)
        self._rv(g)
        self._rv(b)
        self._r = r
        self._g = g
        self._b = b

    @__init__.register
    def _(self, hex:str):
        hex = hex.strip("#")
        if hex[0:2] == "0x":
            hex = hex[2:]
        if len(hex) != 6 or not all(a in hexdigits for a in hex):
            raise ValueError("Bad hex value: %s" % hex)
        r = int(hex[0:2], 16)
        g = int(hex[2:4], 16)
        b = int(hex[5:], 16)
        self._r = r
        self._g = g
        self._b = b

    def _rv(self, v:int):
        if v < 0 or v > 255:
            raise ValueError("Value must be >0 or <256")

    @property
    def r(self):
        return self._r
    
    @r.setter
    def r(self, new:int):
        self._r = _rl(new)

    @property
    def g(self):
        return self._g
    
    @g.setter
    def g(self, new:int):
        self._g = _rl(new)

    @property
    def b(self):
        return self._b
    
    @b.setter
    def b(self, new:int):
        self._b = _rl(new)

    def __mul__(self, c: int | float):
        self.r = _sl(self.r * c)
        self.g = _sl(self.g * c)
        self.b = _sl(self.b * c)

    def __truediv__(self, c: int | float):
        self.r = _sl(self.r / c)
        self.g = _sl(self.b / c)
        self.b = _sl(self.b / c)

    def __floordiv__(self, c: int | float):
        c = int(c)
        self.r = _sl(self.r // c)
        self.g = _sl(self.b // c)
        self.b = _sl(self.b // c)

    def __add__(self, c: int | float):
        self.r = _sl(self.r + c)
        self.g = _sl(self.g + c)
        self.b = _sl(self.b + c)

    @property
    def h(self):
        return self.hsv()[0]

    @property
    def s(self):
        return self.hsv()[1]
    
    @property
    def v(self):
        return self.hsv()[2]

    def hsv(self):
        r = self.r / 255
        g = self.g / 255
        b = self.b / 255
        maxc = max(r, g, b)
        minc = min(r, g, b)
        if maxc == minc:
            return 0.0, 0.0, maxc
        c = (maxc - minc) / maxc
        s = (c/maxc)*100
        hr = r - maxc
        hg = g - maxc
        hb = b - maxc
        h = 0.0
        if maxc == hr:
            h = 0 + hb - hg
        elif maxc == hg:
            h = 2 + hr - hb
        else:
            h = 4 + hg - hr
        h = (h/6) % 1
        return h * 360, s * 100, maxc * 100
"""


def hex_to_rgb(h: str):
    r = int(h[0:2], 16) / 255
    g = int(h[2:4], 16) / 255
    b = int(h[4:], 16) / 255
    return r, g, b


def rgb_to_hex(r, g, b):
    r = int(r * 255)
    g = int(g * 255)
    b = int(b * 255)
    return f"{hex(r)[2:]}{hex(g)[2:]}{hex(b)[2:]}"
