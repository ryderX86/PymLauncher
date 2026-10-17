__all__ = ["set_jump_list", "setup_app_id"]

import logging

from launcher import constants

log = logging.getLogger(__name__)



match constants.OS:
    # pylint: disable=function-redefined
    case "windows":
        # jump lists only exist in >=windows 7 (nt 6.1)
        if float(constants.OS_VER[0:5].rstrip(".")) >= 6.1:
            from .win32 import set_jump_list, setup_app_id
        else:
            log.debug("Windows version is < 6.1, not including jump list func")
    case _:
        def set_jump_list(): ...
        def setup_app_id(): ...