from PySide6.QtCore import Qt, Slot

from launcher import lifecycle


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

    @Slot()
    def _dobind(self):
        if not self._bound:
            self.bind()
            self._bound = True

    def bind(self):
        return
