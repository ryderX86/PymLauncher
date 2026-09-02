"""
crypt32.dll based encryption for accounts.bin
"""

__all__ = ["encrypt", "decrypt", "data_load_hook", "data_save_hook"]
from collections.abc import Buffer
import json
import logging
import socket

from win32 import win32crypt
import pywintypes  # type: ignore

from minecraftlauncher.constants import LAUNCHER_NAME

from .winerr_codes import WinErrorCode

log = logging.getLogger(__name__)

HOST_NAME = socket.gethostname()
ENTROPY = b"PymLauncher accounts store"
DESCRIPTION_PREFIX = f"Accounts data for {LAUNCHER_NAME} on "
DESCRIPTION = "".join((DESCRIPTION_PREFIX, HOST_NAME))


def encrypt(data: str | bytes) -> Buffer:
    if isinstance(data, str):
        data = data.encode("utf-8")

    encrypted_data: bytes = win32crypt.CryptProtectData(
        data, DESCRIPTION, ENTROPY
    )

    if encrypted_data:
        return encrypted_data
    else:
        raise RuntimeError("Failed to encrypt")


def decrypt(data: bytes) -> str:
    data_desc: str
    data_out: bytes
    try:
        data_desc, data_out = win32crypt.CryptUnprotectData(data, ENTROPY)
    except pywintypes.error as err:  # pylint: disable=no-member
        err_code = err.winerror
        if err_code in WinErrorCode:
            error_name = f"{err_code:#x} ({WinErrorCode(err_code).name})"
        else:
            error_name = hex(err_code)
        data_desc = err.strerror
        func = err.funcname
        new = RuntimeError("Failed to decrypt user data")
        new.add_note(f"Error code: {error_name}")
        new.add_note(data_desc)
        new.add_note(f"Function called: {func}")
        raise new from err

    file_host_name = data_desc.replace(DESCRIPTION_PREFIX, "")
    if DESCRIPTION_PREFIX in data_desc and file_host_name != HOST_NAME:
        log.warning(
            "Last host name to save this file is different: "
            "Current host: %r, file's host: %r",
            HOST_NAME,
            file_host_name,
        )
    elif data_desc != DESCRIPTION:
        log.warning(
            "Encrypted data description doesn't match.\n"
            "Default description: '%s'\nEncryption description: '%s'",
            DESCRIPTION,
            data_desc,
        )

    if data_out:
        return data_out.decode("utf-8")
    else:
        raise RuntimeError("Couldn't decrypt data!")


def data_save_hook(j: dict | str) -> Buffer:
    if isinstance(j, dict):
        j = json.dumps(j)

    return encrypt(j)


data_load_hook = decrypt
