class EncryptionUnavailableWarning(UserWarning):
    """
    Warning emitted when the encryption modules cannot be loaded. Should only
    occur on Linux/Unix-based platforms.
    """


class EncryptedDataDecodeError(Exception):
    kwargs: dict

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.kwargs = kwargs

    @property
    def other_machine(self):
        """Whether or not the file was created on another machine."""
        if "other_machine" in self.kwargs and self.kwargs["other_machine"]:
            return True
        return False
