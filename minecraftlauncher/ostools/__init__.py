import logging

from minecraftlauncher.constants import OS, OS_VER

log = logging.getLogger(__name__)


def set_jump_list(): ...


match OS:
    case "windows":
        # jump lists only exist in >=windows 7 (nt 6.1)
        if float(OS_VER[0:5].rstrip(".")) >= 6.1:
            del set_jump_list
            from .win32 import set_jump_list
        else:
            log.debug("Windows version is < 6.1, not including jump list func")
