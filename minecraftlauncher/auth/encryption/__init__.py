"""
Wrapper for platform-dependant encryption functions.

Alternatively, this module defines backup functions if the platform can't be
found in the implemented platform types.
"""

__all__ = ["encrypt", "decrypt", "data_load_hook", "data_save_hook"]
from collections.abc import Buffer
import platform
import logging
import json

from minecraftlauncher.front.window import WarningDialog, WarningType

log = logging.getLogger(__name__)

ENABLED: bool
"""Whether or not the launcher has encryption enabled or not"""

match platform.system():
    case "Windows":
        from .win32_encryption import (
            encrypt,
            decrypt,
            data_load_hook,
            data_save_hook,
        )

        ENABLED = True
    case "Linux":
        try:
            from .linux_encryption import (
                encrypt,
                decrypt,
                data_load_hook,
                data_save_hook,
            )
        except Exception as err:
            log.error("Failed to load Linux encryption module:", exc_info=err)
            WarningDialog.warn(
                None,
                "Failed to load encryption module",
                "Failed to load encryption module for your operating system.\n"
                "If you would like your accounts.bin file to be encrypted, "
                'please install either "gnome-keyring" and "libsecret",\n'
                'or "kwallet" (it\'s better to only install kwallet if you '
                "use KDE) using your system package manager.\n"
                "This warning will only appear once.",
                WarningType.ACCOUNTS_BIN_ENCRYPTION,
                show_once=True,
            )
            from .defaults import (
                encrypt,
                decrypt,
                data_save_hook,
                data_load_hook,
            )
    case _:

        from .defaults import encrypt, decrypt, data_load_hook, data_save_hook

        ENABLED = False
