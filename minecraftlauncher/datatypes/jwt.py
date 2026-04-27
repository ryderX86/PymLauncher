import json
import base64
import binascii


class JWT:
    # TODO: verify_signature()

    header: dict
    payload: dict
    signature: str

    def __init__(self, header: dict, payload: dict, signature: str):
        self.header = header
        self.payload = payload
        self.signature = signature

        if "alg" not in header.keys():
            raise TypeError("Missing 'alg' from JWT header!")


def decode_jwt(jwt: str) -> JWT:
    """
    Decodes a JWT into a dict with `header`, `payload`, and `signature`.

    Raises:
    - `TypeError`, if the type of input isn't either `str` or `None`,
    or raised by the `JWT` class if the header is missing the value for `alg`.
    - `binascii.Error` if the base64 is incorrectly padded or invalid
    characters are present.
    """
    if type(jwt) not in [str, None]:
        raise TypeError(
            f"decode_jwt: Expected str or None, not {type(jwt).__name__}"
        )

    split_jwt: list[str] = jwt.split(".")

    try:
        header: dict = json.loads(
            base64.b64decode(split_jwt[0] + "==").decode()
        )
        payload: dict = json.loads(
            base64.b64decode(split_jwt[1] + "==").decode()
        )
    except binascii.Error as err:
        err.add_note(f"header data: ```{split_jwt[0]}```")
        err.add_note(f"payload data: ```{split_jwt[1]}```")
        raise
    signature = split_jwt[2]

    return JWT(header, payload, signature)
