"""
Module/class loader (mostly) for dialog windows, platform-dependent.

If creating a window mixin, subclass from `._mixins_base.BaseWindowMixin`
"""

__all__ = ["WindowMixins"]

import sys

if sys.platform == "linux":
    from ._mixins_linux import WindowMixins
else:
    # any function or variable on platform specific mixins should at least have
    # a stub in this class:
    from ._mixins_base import BaseWindowMixin as WindowMixins
