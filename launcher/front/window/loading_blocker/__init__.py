import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
)

from launcher import constants, get_qapp

match constants.OS:
    case "windows" | "osx":
        _FLAGS = Qt.WindowType.SplashScreen
    case _:
        _FLAGS = Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint

log = logging.getLogger(__name__)


class LoadingBlockerWindow(QDialog):

    class LoadingBlockerContextManager:
        def __init__(
            self,
            parent: "LoadingBlockerWindow",
            allowed_to_show: bool = True,
            shown_text: str | None = None,
        ):
            self.parent: "LoadingBlockerWindow" = parent
            self.hidden: bool = False
            self.shown: bool = False
            self.shown_text: str | None = shown_text
            """
            Text shown while context manager is active (only for
            `allowed_to_show=True` instances)
            """
            self.allowed: bool = allowed_to_show
            """
            The "mode" of the context manager; if `True`, then __enter__ shows
            the loading blocker and __exit__ hides it, if `False` then it's the
            reverse, __enter__ hides, __exit__ shows.

            Both "modes" are unaffected by their function already being the
            case (with one exception); so if the loading blocker wasn't shown,
            but this is `False` and we're in a context manager, then after
            leaving it, it won't be shown afterwards. If the loading blocker
            *was* open already, it'll close, then re-open after the context
            managing block.

            Same thing with `True`, if it was already open, it won't close
            after leaving the context managing block, however if text is
            supplied to this object, it will save current text, apply the new
            text for the duration of the `with` block, then restore the
            original text, while still not closing/hiding the loading blocker
            afterwards.
            """
            self.previous_text: str = "Loading..."

        def __enter__(self):
            self.parent.recursion_count += 1
            if self.allowed:
                if self.shown_text:
                    self.previous_text = self.parent.current_text
                    self.parent.set_text(self.shown_text)
                if not self.parent.isVisible():
                    self.parent.show()
                    self.shown = True
            else:
                if self.parent.isVisible():
                    self.previous_text = self.parent.current_text
                    self.parent.hide()
                    self.hidden = True
            return self.parent

        def __exit__(self, exc_type, exc, tb):
            if self.allowed:
                if self.shown:
                    self.parent.hide()
                    self.shown = False
                if self.shown_text:
                    self.parent.set_text(self.previous_text)
            else:
                if self.hidden:
                    self.parent.set_text(self.previous_text)
                    self.parent.show()
                    self.hidden = False
            self.parent.recursion_count -= 1

    def __init__(self, parent=None, flags=_FLAGS):
        log.debug("Making loading blocker window")
        super().__init__(parent, flags)
        self.setMinimumSize(500, 360)
        self.setMaximumSize(500, 360)
        self.resize(500, 360)
        self._build_layout()
        self.qapp = get_qapp()
        self._recursion_count = 0

    @property
    def recursion_count(self):
        return self._recursion_count

    if constants.DEV:

        @recursion_count.setter
        def recursion_count(self, new_val: int):
            self._recursion_count = new_val
            if self._recursion_count > 5:
                log.warning(
                    "Heavy recursion with context managers! Current: %d",
                    self._recursion_count,
                )

    else:

        @recursion_count.setter
        def recursion_count(self, new_val: int):
            self._recursion_count = new_val

    def _build_layout(self):
        _layout = QVBoxLayout(self)

        self.label = QLabel("Loading...", wordWrap=True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        _layout.addWidget(self.label)
        return

    def set_text(self, text: str = "Loading..."):
        if not text.endswith("..."):
            text = "".join((text, "..."))
        self.label.setText(text)
        self.qapp.processEvents()

    @property
    def current_text(self):
        return self.label.text()

    def open(self) -> None:
        super().open()
        self.qapp.processEvents()

    def show(self) -> None:
        super().show()
        self.qapp.processEvents()

    def hide(self):
        super().hide()
        self.set_text()

    def shown(self, text: str | None = None):
        """
        Returns a context manager class instance with __enter__ and __exit__
        methods to:

        1. Ensure the loading blocker *is* visible during a process, showing it
        if it's not already shown
        2. After __exit__ is called by the `with` statement, if the blocker
        wasn't open before entering the context window, it'll hide it, however
        if it was already showing before, it'll ignore it and leave it up.
        3. If text is provided in the argument, it'll be supplied to the
        instance which will then set the text for the duration of the context
        window, then restore whatever text was previously present for the
        loader.
        """
        return self.LoadingBlockerContextManager(self, True, text)

    def hidden(self):
        """
        Returns a context manager class instance with __enter__ and __exit__
        methods to:

        1. Ensure the loading blocker isn't visible during a process, hiding it
        if it's visible
        2. After __exit__ is called (after the 'with:' statement is finished),
        show the loading blocker again with the previous text.
        """
        return self.LoadingBlockerContextManager(self, False)
