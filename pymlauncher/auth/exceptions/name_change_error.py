class NameChangeError(Exception):
    def __init__(self, name_change_err: str):
        self.details = name_change_err
        super().__init__(f"Profile name change failed: {name_change_err}")
