from PySide6.QtGui import QValidator

from .store_results import store_results, QValidatorWithStoredResults


class ProfileResolutionTextValidator(QValidatorWithStoredResults):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resolutions: list[str] = []

    def set_resolutions(self, resolution_list: list[str]):
        self.resolutions = resolution_list

    @store_results
    def validate(
        self, a0: str | None, a1: int
    ) -> tuple[QValidator.State, str, int]:
        if not a0:
            return self.State.Intermediate, self.resolutions[0], 0
        if a0 == "Auto":
            return self.State.Acceptable, a0, a1

        # QOL autofill 1080p -> 1920x1080
        if a0[:-1].isdigit() and a0[-1] == "p":
            if int(a0[:-1]) % 8 == 0:
                h = int(a0[:-1])
                w = (h // 9) * 16
                a0 = f"{w}x{h}"
        a0 = a0.replace("*", "x").replace(".", "x").replace(":", "x")
        a0 = a0.replace(" ", "")
        sel_res = a0.split("x")
        if (
            (len(sel_res) < 2 and sel_res[0].isdigit())
            or sel_res[0].isdigit()
            and not sel_res[1]
        ):
            return self.State.Intermediate, a0, a1
        elif sel_res[0].isdigit() and sel_res[1].isdigit():
            w = int(sel_res[0])
            h = int(sel_res[1])
            if w > 10000 or h > 10000:
                return self.State.Invalid, a0, a1
            elif w < 100 or h < 100:
                return self.State.Intermediate, a0, a1
            return self.State.Acceptable, a0, a1
        return self.State.Invalid, self.resolutions[0], 0

    def fixup(self, arg__0: str):
        if not self.isValid():
            return self.resolutions[0]
        return arg__0
