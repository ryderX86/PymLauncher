from string import digits

from PySide6.QtGui import QValidator

from .store_results import store_results, QValidatorWithStoredResults

ALLOWED_LETTERS = set("BbKkMmGg")
DIGITS = set(digits)


class ProfileRAMValidator(QValidatorWithStoredResults):
    @store_results
    def validate(
        self, arg__1: str, arg__2: int
    ) -> tuple[QValidator.State, str, int]:
        if not arg__1:
            return (QValidator.State.Intermediate, arg__1, arg__2)
        elif not all(c in DIGITS or c in ALLOWED_LETTERS for c in arg__1):
            return (
                QValidator.State.Invalid,
                "".join(
                    c for c in arg__1 if c in ALLOWED_LETTERS or c in DIGITS
                ),
                arg__2,
            )
        elif not all(c in DIGITS for c in arg__1[:-1]):
            return (QValidator.State.Invalid, arg__1, arg__2)
        elif arg__1[0] not in DIGITS:
            return (QValidator.State.Invalid, arg__1, arg__2)
        elif arg__1[-1] not in ALLOWED_LETTERS:
            return QValidator.State.Intermediate, arg__1, arg__2
        return QValidator.State.Acceptable, arg__1, arg__2

    def fixup(self, text: str):
        if not text:
            text = "512M"
        elif not all(c in DIGITS or c in ALLOWED_LETTERS for c in text):
            text = "".join(
                c for c in text if c in DIGITS or c in ALLOWED_LETTERS
            )
        elif not all(c in DIGITS for c in text[:-1]):
            text = "".join([(c for c in text[:-1] if c in DIGITS), text[-1]])
        elif text[0] not in DIGITS:
            text = "512M"
        elif text[-1] not in ALLOWED_LETTERS:
            if len(text) < 3:
                text = "".join([text, "G"])
            elif len(text) > 4:
                text = "".join([text, "K"])
            else:
                text = "".join([text, "M"])
        return text
