# pylint: disable=e1101
from typing import Callable, Any

from PySide6.QtGui import QValidator

_results_cache: dict[int, tuple[QValidator.State, str, int] | None] = {}


def store_results(
    func: Callable[[Any, str, int], tuple[QValidator.State, str, int]],
):
    """
    Function decorator for QValidator subclasses to store the previous results.

    When given `QValidator.validate`, it will return a new function with a
    `last()` method that returns the last known return of `validate(...)`.
    """
    func_hash = hash(func)
    iterations = 0
    while func_hash in _results_cache:
        iterations += 1
        if iterations > 255:
            raise RuntimeError(
                f"Couldn't get unique hash for function {func.__name__}"
            )
        func_hash += 7
    _results_cache[func_hash] = QValidator.State.Acceptable, "", 0

    def wrapped_func(*args, **kwargs) -> tuple[QValidator.State, str, int]:
        result = func(*args, **kwargs)
        _results_cache[func_hash] = result
        return result

    def get_result_from_wrapped():
        return _results_cache[func_hash]

    setattr(wrapped_func, "last", get_result_from_wrapped)
    return wrapped_func


class QValidatorWithStoredResults(QValidator):
    def __init__(self, *args, **kwargs):
        if not getattr(self.validate, "last", None):
            raise SyntaxError(
                "This class must use the 'store_results' decorator if "
                "'validate()' is overridden."
            )
        super().__init__(*args, **kwargs)

    validate = store_results(QValidator.validate)  # type: ignore

    def isValid(self):
        # @store_results adds this method
        state, _, _ = self.validate.last()  # type: ignore
        match state:
            case QValidator.State.Invalid | QValidator.State.Intermediate:
                return False
            case QValidator.State.Acceptable:
                return True
            case _:
                return False
