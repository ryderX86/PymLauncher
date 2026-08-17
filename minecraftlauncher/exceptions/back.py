from . import InstallException


class Log4JConfigReadError(InstallException):
    """
    Failed to parse Log4J config file to patch for launcher compatibility.
    """

    def __init__(self, filename: str, lineno: int, offset: int):
        self.lineno = lineno
        self.offset = offset
        super().__init__(
            self,
            f"XML parsing error in {filename!r} at line {lineno}, column {offset}",
        )


class AssetDownloadError(InstallException):
    """
    Generic asset download failure. Could be a game asset, or Log4J config.
    """
