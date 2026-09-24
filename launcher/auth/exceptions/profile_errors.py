class BaseProfileError(Exception):
    class_error_code = 0
    ui_msg = "An unknown error occured while fetching/updating your profile."

    def __init__(
        self,
        status_code: int = -1,
        path: str = "unknown",
        error: str = "Unknown",
        error_message: str = "An unknown error occured",
    ):
        if path and error and error_message:
            super().__init__(
                f"{path.rstrip("/")}: {status_code}: {error} - {error_message}"
            )
        else:
            super().__init__(f"{status_code}: {self.ui_msg}")
        self.error = error
        self.path = path
        self.status_code = status_code

    @classmethod
    def auto_select_class(cls, status_code: int):
        for subclass in cls.__subclasses__():
            if subclass.class_error_code == status_code:
                return subclass

        return cls


class ProfileNotFoundError(BaseProfileError):
    ui_msg = (
        "Your profile could not be found, please sign in at"
        " https://minecraft.net and ensure your profile has been created."
    )
    class_error_code = 404
