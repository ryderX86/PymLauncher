from warnings import deprecated
import platform

from PySide6.QtGui import QValidator

from launcher.functions import is_path_valid


@deprecated("Use PySide6.QRegularExpressionValidator() instead.")
class FilePathValidator(QValidator):
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
                return arg__1.replace("/", "\\")
            return arg__1
