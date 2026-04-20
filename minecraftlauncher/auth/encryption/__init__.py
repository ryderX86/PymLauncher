"""
Wrapper for platform-dependant encryption functions.

Alternatively, this module defines backup functions if the platform can't be
found in the implemented platform types.
"""
__all__ = ["encrypt", "decrypt", "data_load_hook", "data_save_hook"]
from typing import ByteString
import platform
import logging
import json

from minecraftlauncher.constants import WANT_ENCRYPTION

log = logging.getLogger(__name__)

match platform.system(), WANT_ENCRYPTION:
    case "Windows", True:
        from .win32_encryption import (
            encrypt, decrypt, data_load_hook, data_save_hook)
    case _:
        log.warning(
            "Platform is not supported for encryption, user login info won't "
            "be safe")
        
        def encrypt(data:str|bytes) -> ByteString:
            log.warning("User data is NOT secure; encryption is not "
                        "implemented on this platform.")
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data
        
        def decrypt(data:bytes):
            return data.decode("utf-8")
        
        def data_save_hook(j:dict|str) -> ByteString:
            if isinstance(j, dict):
                j = json.dumps(j)
            
            return j.encode("utf-8")
        
        data_load_hook = decrypt
