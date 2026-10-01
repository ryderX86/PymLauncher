from typing import ParamSpec, Concatenate
from collections.abc import Callable

from PySide6.QtCore import Qt, Slot

from launcher import lifecycle

P = ParamSpec("P")
type S = BindingMixin


def _decorate_init(
    func: Callable[Concatenate[S, P], None],
) -> Callable[Concatenate[S, P], None]:
    def wrapper(self: S, *args: P.args, **kwargs: P.kwargs) -> None:
        func(self, *args, **kwargs)
        self._checkbind()
        return

    return wrapper


class BindingMixin:
    """
    Mixin class for QObject classes that runs a subclass's `bind()` function
    as soon as the Qt event loop begins.
    """

    _bound: bool

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bound = False
        lifecycle.bootstrap_done.connect(
            self._dobind, Qt.ConnectionType.UniqueConnection
        )

    def __init_subclass__(cls) -> None:
        cls.__init__ = _decorate_init(cls.__init__)

    def _checkbind(self):
        if lifecycle.bootstrap_already_run:
            self._dobind()

    @Slot()
    def _dobind(self):
        if not self._bound:
            self.bind()
            self._bound = True

    def bind(self):
        return
