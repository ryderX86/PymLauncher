from string import ascii_letters, digits
from datetime import datetime
import logging

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLineEdit,
)


from minecraftlauncher.auth.exceptions import (
    TooManyRequestsError,
    NameChangeError,
)
from minecraftlauncher.front.window.skin_change import QCloseEvent
from minecraftlauncher.functions.error_box import error_box
from minecraftlauncher.back import account_manager

log = logging.getLogger(__name__)


class UsernameInputValidator(QValidator):
    allowed_chars = "".join([*ascii_letters, *digits, "_"])

    def validate(self, a0: str, a1: int) -> tuple[QValidator.State, str, int]:
        if len(a0) > 16:
            return self.State.Invalid, a0[:16], a1
        elif len(a0) < 3:
            return self.State.Intermediate, a0, a1
        elif not all(c in self.allowed_chars for c in a0):
            return self.State.Invalid, a0, a1
        return self.State.Acceptable, a0, a1


class UsernameChangeWindow(QDialog):
    username_changed = Signal(str)  # username
    validator = UsernameInputValidator()
    available_names_cache: set[str]
    unavailable_names_cache: set[str]
    unavailable_names_reason: dict[str, str]

    current_button_timer: QTimer

    def __init__(self, parent=None):
        super().__init__(parent)
        assert account_manager.active_account
        self.account = account_manager.fetch_account(
            account_manager.active_account
        )
        if not self.account:
            raise RuntimeError("No active account!")
        if not self.account.profile or not self.account.has_profile:
            raise RuntimeError(
                "Account doesn't have a loaded profile. Shouldn't have been "
                "able to open this window!"
            )

        self.profile = self.account.profile
        self.available_names_cache = set()
        self.unavailable_names_cache = set()
        self.unavailable_names_reason = {}
        self.current_button_timer = QTimer(self)
        self.current_button_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.current_button_timer.setSingleShot(True)
        self.button_text_timer = QTimer(self)
        self.button_text_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.button_text_timer.setSingleShot(False)
        self.button_text_timer.setInterval(200)
        self._build_ui()

    def exec(self) -> int:
        can_change_name, last_change = self.profile.check_can_change_name()
        if can_change_name:
            return super().exec()
        else:
            error_box(
                "Sorry, you cannot change your name at this moment.\n"
                f"Last username change: {last_change}"
            )
            return 0

    def _build_ui(self):
        root = QVBoxLayout(self)

        row1_w = QWidget()
        row1 = QHBoxLayout(row1_w)

        label = QLabel("Username:")
        row1.addWidget(label)

        self.username_edit = QLineEdit()
        self.username_edit.setValidator(self.validator)
        self.username_edit.setPlaceholderText("Steve")
        self.username_edit.setText(self.profile.name)
        self.username_edit.textChanged.connect(self._on_text_change)
        row1.addWidget(self.username_edit)

        root.addWidget(row1_w)

        self.name_reason = QLabel("An unknown error occured.")
        self.name_reason.setProperty("danger", True)
        self.name_reason.setHidden(True)
        root.addWidget(self.name_reason)

        row3_w = QWidget()
        row3 = QHBoxLayout(row3_w)
        row3.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row3.addWidget(cancel)

        self.check_name_btn = QPushButton("Check Name")
        self.check_name_btn.setFixedWidth(150)
        self.check_name_btn.clicked.connect(self._check_name_button)
        self.check_name_btn.setDisabled(True)
        row3.addWidget(self.check_name_btn)
        self.current_button_timer.timeout.connect(lambda: self._end_cooldown)
        self.button_text_timer.timeout.connect(self._update_button_text)

        self.set_name_btn = QPushButton("Change Name")
        self.set_name_btn.setFixedWidth(150)
        row3.addWidget(self.set_name_btn)
        self.set_name_btn.setHidden(True)

        root.addWidget(row3_w)

    def _start_cooldown(self, ms: int):
        self.current_button_timer.stop()
        self.button_text_timer.stop()
        self.current_button_timer.setInterval(ms)
        self.current_button_timer.start()
        self.button_text_timer.start()

    def _update_button_text(self):
        rem_time = self.current_button_timer.remainingTime() // 1000
        self.check_name_btn.setText(f"Wait {rem_time}s...")

    def _end_cooldown(self):
        self.check_name_btn.setDisabled(False)
        self.button_text_timer.stop()
        self.current_button_timer.stop()
        self.check_name_btn.setText("Check Name")
        self._on_text_change(self.username_edit.text())

    def _on_text_change(self, text: str):
        if not self.profile.is_na_rl_active():
            self.check_name_btn.setText("Check Name")
        if text == self.profile.name:
            self.check_name_btn.setEnabled(False)
            self.check_name_btn.setDisabled(True)
            self.set_name_btn.setHidden(True)
            self.check_name_btn.setHidden(False)
        elif self.profile.is_na_rl_active():
            self.check_name_btn.setDisabled(True)
            self.set_name_btn.setHidden(True)
            self.check_name_btn.setHidden(False)
            if not self.current_button_timer.isActive():
                assert self.profile.na_rate_limit_end
                self._start_cooldown(
                    int(
                        (
                            self.profile.na_rate_limit_end - datetime.now()
                        ).total_seconds()
                        * 1000
                    )
                )
        elif text in self.available_names_cache:
            self.check_name_btn.setEnabled(False)
            self.check_name_btn.setHidden(True)
            self.set_name_btn.setHidden(False)
        elif text in self.unavailable_names_cache:
            self.check_name_btn.setEnabled(True)
            self.check_name_btn.setHidden(False)
            self.set_name_btn.setHidden(True)
            self.name_reason.setText(
                self.unavailable_names_reason.get(
                    text, "Name is already taken."
                )
            )
        else:
            self.check_name_btn.setEnabled(True)
            self.set_name_btn.setHidden(True)
            self.check_name_btn.setHidden(False)

    def closeEvent(self, arg__1: QCloseEvent) -> None:
        self.current_button_timer.stop()
        self.button_text_timer.stop()
        return super().closeEvent(arg__1)

    def accept(self) -> None:
        self.current_button_timer.stop()
        self.button_text_timer.stop()
        return super().accept()

    def reject(self) -> None:
        self.current_button_timer.stop()
        self.button_text_timer.stop()
        return super().reject()

    def destroy(self, *args, **kwargs) -> None:
        self.current_button_timer.stop()
        self.button_text_timer.stop()
        return super().destroy(*args, **kwargs)

    def _change_name_button(self):
        name = self.username_edit.text()
        if name not in self.available_names_cache:
            log.warning("Change name button shouldn't have been activated!")
            self.set_name_btn.setHidden(True)
            self.check_name_btn.setHidden(False)
            return
        try:
            self.profile.change_username(name)
        except NameChangeError as err:
            error_box(f"Unable to change name: {err.details}")
            self.current_button_timer.stop()
            self.reject()

    def _check_name_button(self):
        self.check_name_btn.setDisabled(True)
        self.check_name_btn.setText("Checking...")
        name = self.username_edit.text()
        try:
            available, reason = self.profile.check_name_available(name)
        except ValueError as err:
            log.warning("Didn't validate username enough!", exc_info=err)
            self.check_name_btn.setDisabled(False)
            return
        except TooManyRequestsError as err:
            self._start_cooldown(int(err.wait_timeout.total_seconds() * 1000))
            error_box(
                "Cannot check if username is available.\n"
                "Too many requests.\n"
                f"Wait {int(err.wait_timeout.total_seconds())}s and try again."
            )
            return
        else:
            assert self.profile.na_rate_limit_end
            cd = self.profile.na_rate_limit_end - datetime.now()
            self._start_cooldown(int(cd.total_seconds() * 1000))
            if available:
                self.check_name_btn.setHidden(True)
                self.set_name_btn.setHidden(False)
                self.unavailable_names_cache.discard(name)
                if name in self.unavailable_names_reason:
                    del self.unavailable_names_reason[name]
                self.available_names_cache.add(name)
                QTimer.singleShot(
                    600000, lambda: self.available_names_cache.discard(name)
                )
                self.name_reason.setHidden(True)
            else:
                assert reason  # if unavailable there WILL be a string
                self.name_reason.setText(reason)
                self.name_reason.setHidden(False)
                self.unavailable_names_cache.add(name)
                self.unavailable_names_reason[name] = reason
                QTimer.singleShot(
                    600000, lambda: self.unavailable_names_cache.discard(name)
                )
                QTimer.singleShot(
                    600000, lambda: self.unavailable_names_reason.pop(name, "")
                )
