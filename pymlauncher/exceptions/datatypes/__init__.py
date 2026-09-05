class ProfileError(Exception):
    pass


class InvalidVersionIdError(RuntimeError, ProfileError):
    pass
