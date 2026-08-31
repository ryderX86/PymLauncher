class EncryptionUnavailableWarning(UserWarning):
    """
    Warning emitted when the encryption modules cannot be loaded. Should only
    occur on Linux/Unix-based platforms.
    """
