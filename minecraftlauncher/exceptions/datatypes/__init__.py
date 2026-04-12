from .XstsAuthError import XstsAuthError

class ProfileError(Exception):
    pass

class InvalidVersionIdError(RuntimeError, ProfileError):
    pass