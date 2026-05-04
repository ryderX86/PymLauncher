# pylint: disable=w0611
import platform
import logging

from . import build_hooks, CWD

logging.debug("Working directory: %s", CWD)

match platform.system():
    case "Windows":
        from . import build_w32
