"""
Wrapper for platform-dependant encryption functions.

Alternatively, this module defines backup functions if the platform can't be
found in the implemented platform types.
"""

__all__ = ["encrypt", "decrypt", "data_load_hook", "data_save_hook"]
import logging
import platform
import warnings

from launcher.exceptions.encryption import (
    EncryptionUnavailableWarning,
)

log = logging.getLogger(__name__)

ENABLED: bool
"""Whether or not the launcher has encryption enabled or not"""


# this function and these checks are removed on compilation for all OSes except
# linux, since some installs may not have a valid keyring but others might and
# we need to account for that; nuitka should trim the match statement but it's
# not guarenteed unless we replace platform.system() calls
def run_import():
    # pylint: disable=import-outside-toplevel
    global encrypt, decrypt, data_load_hook, data_save_hook, ENABLED
    match platform.system():
        case "Windows":
            from .win32_encryption import (
                data_load_hook,
                data_save_hook,
                decrypt,
                encrypt,
            )

            ENABLED = True
        case "Linux":
            try:
                from .linux_encryption import (
                    data_load_hook,
                    data_save_hook,
                    decrypt,
                    encrypt,
                )

                ENABLED = True
            except Exception as err:
                log.error(
                    "Failed to load Linux encryption module:", exc_info=err
                )
                warnings.warn(
                    EncryptionUnavailableWarning(
                        f"Failed to load encryption modules ({type(err)}).\n"
                        "Please make sure either GNOME Keyring or KDE Wallet "
                        "are installed on your system."
                    )
                )
                from .no_encryption import (
                    data_load_hook,
                    data_save_hook,
                    decrypt,
                    encrypt,
                )
        case _:

            from .no_encryption import (
                data_load_hook,
                data_save_hook,
                decrypt,
                encrypt,
            )

            ENABLED = False


run_import()
