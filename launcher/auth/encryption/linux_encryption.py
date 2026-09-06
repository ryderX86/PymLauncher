"""
`keyring` package based encryption for accounts.bin
"""

from collections.abc import Buffer
import json
import logging
import secrets

from cryptography.fernet import Fernet, InvalidToken

logging.getLogger("keyring").setLevel(
    logging.CRITICAL
)  # pylint: disable=C0413
import keyring

from launcher.constants import LAUNCHER_NAME

log = logging.getLogger(__name__)


keyring.get_keyring()


enc_key = keyring.get_credential(LAUNCHER_NAME, "encryption-key")
if not enc_key:
    log.debug(
        "Creating new encryption key for launcher and storing in keyring"
    )

    secret = "".join([secrets.token_urlsafe(32), "==="])
    key = Fernet(secret)
    keyring.set_password(LAUNCHER_NAME, "encryption-key", secret)
else:
    key = Fernet(enc_key.password)


def encrypt(data: str | bytes) -> Buffer:
    if isinstance(data, str):
        data = data.encode("utf-8")

    return b"".join([b"ENC", key.encrypt(data)])


def decrypt(data: bytes) -> str:
    if data[0:3] != b"ENC":
        log.warning("Likely unencrypted string used in decrypt()")
        return data.decode("utf-8")

    data = data[3:]
    try:
        return key.decrypt(data).decode("utf-8")
    except InvalidToken as err:
        log.error("Failed decryption:", exc_info=err)
        new = RuntimeError("Failed to decrypt user data")
        raise new from err


def data_save_hook(j: dict | str) -> Buffer:
    if isinstance(j, dict):
        j = json.dumps(j)

    return encrypt(j)


data_load_hook = decrypt
