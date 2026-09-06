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


class JavaDownloadError(InstallException):
    """
    Generic download failure for a Java version.
    """


class JavaIndexError(JavaDownloadError):
    """
    The asset index for this Java version is invalid
    """


class MarkExecutableError(JavaDownloadError):
    """
    Couldn't mark downloaded Java binary as executable
    """

    @property
    def permission_error(self) -> bool:
        """Returns `True` if the cause/context is a `PermissionError`"""
        if isinstance(self.context, PermissionError):
            return True
        return False

    @property
    def context(self):
        if self.__cause__ is not None:
            return self.__cause__
        elif self.__context__ is not None:
            return self.__context__
        return None
