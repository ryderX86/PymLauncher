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
    case _:

        def encrypt(data: str | bytes) -> Buffer:
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data

        def decrypt(data: bytes):
            return data.decode("utf-8")

        def data_save_hook(j: dict | str) -> Buffer:
            if isinstance(j, dict):
                j = json.dumps(j)

            return j.encode("utf-8")

        data_load_hook = decrypt
        ENABLED = False
