from collections.abc import Callable
from inspect import _empty, signature
from typing import ParamSpec, TypeVar, get_type_hints
import logging
import sys

from PySide6.QtCore import (
    QEvent,
    QEventLoop,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QCloseEvent,
    QInputEvent,
    QKeyEvent,
)
from PySide6.QtWidgets import QApplication, QMainWindow, QProgressDialog

from launcher import lifecycle
from launcher.front.window.loading_blocker import LoadingBlockerWindow

log = logging.getLogger(__name__)


class LROInputEventFilter(QObject):
    def __init__(self, watched: QObject):
        self._watched = watched
        super().__init__()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        match watched, event:
            case (_, QCloseEvent() | QInputEvent() | QKeyEvent()):
                return True
            case _, QEvent() if event.type() == QEvent.Type.ActivationChange:
                return True
        match event.type():
            case QEvent.Type.WindowActivate:
                return True
        return super().eventFilter(watched, event)


class LROThread(QThread):
    returned_result = Signal(tuple)
    exception = Signal(Exception)

    P = ParamSpec("P")
    T = TypeVar("T")
    _result: object | None = None
    _exception: Exception | None = None
    _dialog: QProgressDialog | None

    def __init__(
        self,
        parent=None,
        dialog_instance_or_type: (
            type[QProgressDialog] | QProgressDialog | None
        ) = LoadingBlockerWindow,
        *,
        msg: str | None = None,
        max_expected_time: int | float | None = None,
    ):
        self.affinity = QThread.currentThread()
        if isinstance(dialog_instance_or_type, type):
            self._dialog = dialog_instance_or_type(parent)
        elif dialog_instance_or_type is None:
            self._dialog = None
        else:
            self._dialog = dialog_instance_or_type
        if self._dialog is not None:
            for w in QApplication.topLevelWidgets():
                if isinstance(w, QMainWindow):
                    self._dialog.setParent(w)
            if msg:
                self._dialog.setLabelText(msg)
            self._dialog.setCancelButton(None)
            self._dialog_old_flags = self._dialog.windowFlags()
            self._dialog_old_modality = self._dialog.windowModality()
            self._dialog.setWindowFlags(
                self._dialog.windowFlags() | Qt.WindowType.SplashScreen
            )
            self._dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            if max_expected_time is not None:
                self._dialog.setMinimumDuration(int(max_expected_time * 1000))
            else:
                self._dialog.setMinimumDuration(0)
        super().__init__(parent)

    @Slot(Exception)
    def _on_exception(self, exc: Exception):
        self._exception = exc

    @Slot(object)
    def _on_result(self, result: object):
        self._result = result

    def start(self, /, priority=QThread.Priority.NormalPriority) -> None:
        raise NotImplementedError("Use go() instead.")

    @property
    def blocker(self):
        return self._dialog

    def run(self):
        try:
            result = self._func(*self._func_args, **self._func_kwargs)
        except Exception as err:
            self.exception.emit(err)
        else:
            self.returned_result.emit(result)

    def go(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        self._func = func
        self._func_args = args
        self._func_kwargs = kwargs
        if QThread.currentThread() != self.affinity:
            raise RuntimeError("Bad thread affinity")
        loop = QEventLoop()
        self.exception.connect(
            self._on_exception, Qt.ConnectionType.BlockingQueuedConnection
        )
        self.exception.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        self.returned_result.connect(
            self._on_result, Qt.ConnectionType.BlockingQueuedConnection
        )
        self.returned_result.connect(
            loop.quit, Qt.ConnectionType.QueuedConnection
        )
        super().start(QThread.Priority.NormalPriority)
        if self._dialog:
            if sys.platform not in {"win32"}:
                ef = LROInputEventFilter(lifecycle.qapp)
                lifecycle.qapp.installEventFilter(ef)
            self._dialog.open()
            loop.exec()
            self._dialog.close()
            self._dialog.setWindowFlags(self._dialog_old_flags)
            self._dialog.setWindowModality(self._dialog_old_modality)
            if sys.platform not in {"win32"}:
                QApplication.processEvents()
                lifecycle.qapp.removeEventFilter(ef)  # type: ignore
        else:
            loop.exec()
        if self._exception:
            raise self._exception
        if signature(self._func).return_annotation is not _empty:
            if not isinstance(
                self._result,
                (
                    rt := get_type_hints(self._func).get(
                        "return", signature(self._func).return_annotation
                    )
                ),
            ):
                print(get_type_hints(self._func))
                raise TypeError(
                    f"Function {self._func.__name__} returned invalid type: "
                    f"{type(self._result).__name__} (expected any of {rt!r})"
                )
        return self._result  # type: ignore


P = ParamSpec("P")
R = TypeVar("R")


def run_lro(
    msg: str, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
) -> R:
    """
    Creates a QThread & QEventLoop to handle a long-running operation without
    freezing the UI, and immediately shows a LoadingBlockerWindow for the
    duration of the function.

    Returns the result of the passed function called with the provided `*args`
    and `**kwargs`, or re-raises the thrown exception from the main thread.
    """
    return LROThread(msg=msg).go(func, *args, **kwargs)


def run_potential_lro(
    max_expected_secs: int | float,
    msg: str,
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """
    Creates a QThread & QEventLoop to handle a long-running operation without
    freezing the UI, with a LoadingBlockerWindow opening if `max_expected_secs`
    is surpassed, showing it for the rest of the function's duration.

    Returns the result of the passed function called with the provided `*args`
    and `**kwargs`, or re-raises the thrown exception from the main thread.
    """
    return LROThread(msg=msg, max_expected_time=max_expected_secs).go(
        func, *args, **kwargs
    )
