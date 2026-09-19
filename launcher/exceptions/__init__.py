class EncryptedDataDecodeError(Exception):
    pass


class InstallException(Exception):
    """
    Base class for errors while installing/verifying the installation of the
    game
    """


class InvalidAssetError(Exception):
    """
    An asset related to launching the game is invalid.

    Check the `filename` property for more information.
    """

    filename: str
    json_content: str | None

    def __init__(
        self, msg: str, filename: str, json_content: str | None = None
    ) -> None:
        super().__init__(msg)
        self.filename = filename
        self.json_content = json_content
