from PySide6.QtGui import QScreen, QValidator

from .store_results import QValidatorWithStoredResults, store_results

COMMON_RESOLUTIONS = [
    (854, 480),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
]


class ProfileResolutionTextValidator(QValidatorWithStoredResults):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resolutions: list[str] = []

    def set_resolutions(self, screen: QScreen) -> list[str]:
        res_list = [f"{w}x{h}" for w, h in COMMON_RESOLUTIONS]
        geo = screen.geometry()
        if screen:
            sw, sh = geo.width(), geo.height()
            for frac in [1.0, 0.8, 0.75, 0.6]:
                w = int(sw * frac)
                h = int(sh * frac)
                res = f"{w}x{h}"
                if res not in res_list:
                    res_list.append(res)
            for x, y in COMMON_RESOLUTIONS:
                if x > sw or y > sh:
                    res_list.remove(f"{x}x{y}")
        self.resolutions = sorted(res_list, key=lambda r: int(r.split("x")[0]))
        self.resolutions.insert(0, "Automatic")
        return self.resolutions

    @store_results
    def validate(
        self, a0: str | None, a1: int
    ) -> tuple[QValidator.State, str, int]:
        if not a0:
            return self.State.Acceptable, "Automatic", 0
        if a0 == "Automatic":
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
