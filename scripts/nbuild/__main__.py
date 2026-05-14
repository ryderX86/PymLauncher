# pylint: disable=w0611
import platform
import logging

from . import CWD, bump_build_number, FLAGS, BuildFlags

logging.debug("Working directory: %s", CWD)

match platform.system():
    case "Windows":
        from . import build_w32

if not FLAGS & BuildFlags.NO_BUILD_BUMP:
    bump_build_number()
