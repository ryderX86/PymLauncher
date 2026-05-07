from collections.abc import Buffer
import json


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
