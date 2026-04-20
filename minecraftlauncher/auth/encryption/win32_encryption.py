"""
crypt32.dll based encryption for accounts.bin
"""
__all__ = ["encrypt", "decrypt", "data_load_hook", "data_save_hook"]
from typing import ByteString
import logging
import json

from win32 import win32crypt
import pywintypes # type: ignore

from minecraftlauncher.constants import LAUNCHER_NAME
from .winerr_codes import WinErrorCode

log = logging.getLogger(__name__)

protect_data = win32crypt.CryptProtectData
unprotect_data = win32crypt.CryptUnprotectData

ENTROPY = b"WTF IS A KILOMETER!!!!!!!!!!"
DESCRIPTION = "Accounts data for %s" % LAUNCHER_NAME

def encrypt(data:str|bytes) -> ByteString:
    if isinstance(data, str):
        data = data.encode("utf-8")

    encrypted_data = protect_data(data, DESCRIPTION, ENTROPY)

    if encrypted_data:
        return encrypted_data
    else:
        raise RuntimeError("Failed to encrypt")

def decrypt(data:bytes) -> str:
    try:
        desc, data_out = unprotect_data(data, ENTROPY)
    except pywintypes.error as err:
        err_code = err.winerror
        if err_code in WinErrorCode:
            error_name = "%s (%s)" % (hex(err_code),
                                      WinErrorCode(err_code).name)
        else:
            error_name = hex(err_code)
        desc = err.strerror
        func = err.funcname
        new = RuntimeError("Failed to decrypt user data")
        new.add_note("Error code: %s" % error_name)
        new.add_note(desc)
        new.add_note("Function called: %s" % func)
        raise new from err

    if desc != DESCRIPTION:
        log.warning(
            "Encrypted data description doesn't match. "
            "Something very likely went wrong.\n"
            "Default description: '%s'\nEncryption description: '%s'"
            % (DESCRIPTION, desc))

    if data_out:
        return data_out.decode("utf-8")
    else:
        raise RuntimeError("Couldn't decrypt data!")
    
def data_save_hook(j:dict|str) -> ByteString:
    if isinstance(j, dict):
        j = json.dumps(j)
    
    return encrypt(j)

data_load_hook = decrypt