import platform

from PySide6.QtGui import QValidator

from minecraftlauncher.functions import is_path_valid
from .store_results import store_results, QValidatorWithStoredResults


class FilePathValidator(QValidatorWithStoredResults):
    @store_results
    def validate(
        self, arg__1: str, arg__2: int
    ) -> tuple[QValidator.State, str, int]:
        arg__1 = self.fixup(arg__1)
        if not arg__1:
            return QValidator.State.Acceptable, arg__1, arg__2
        if is_path_valid(arg__1):
            return QValidator.State.Acceptable, arg__1, arg__2
        else:
            return QValidator.State.Intermediate, arg__1, arg__2

    if platform.system() == "Windows":

        def fixup(self, arg__1: str) -> str:
            if arg__1:
                return super().fixup(arg__1.replace("/", "\\"))
            return super().fixup(arg__1)
