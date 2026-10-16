from textwrap import dedent
import logging

from PySide6.QtCore import QFile, QSize, Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from launcher import constants
from launcher.front.qt.widgets import Header1
from launcher.front.styles import get_fonts

log = logging.getLogger(__name__)


def al(w):
    w.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    return w


class AboutWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.lo = QVBoxLayout()
        self.setLayout(self.lo)

        self.lo.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        header_layout = QHBoxLayout()

        icon_display_proxy = QLabel()
        qicon = QIcon(":/icon.ico")
        pixmap = qicon.pixmap(QSize(64, 64))
        icon_display_proxy.setPixmap(pixmap)
        header_layout.addWidget(icon_display_proxy, 0)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 8, 0, 8)
        title_header = Header1(constants.LAUNCHER_NAME)
        title_layout.addWidget(title_header, 0)
        ver = QLabel(f"Version {constants.LAUNCHER_VERSION}")
        title_layout.addWidget(ver, 0)
        header_layout.addLayout(title_layout, 0)
        # title_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.lo.addLayout(header_layout, 0)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.tab_widget = QTabWidget()
        self.lo.addWidget(self.tab_widget)
        self._create_main_tab()
        self._create_acknowledgements_tab()

        button_layout = QHBoxLayout()
        about_qt = QPushButton(
            QIcon(
                QApplication.style().standardIcon(
                    QStyle.StandardPixmap.SP_TitleBarMenuButton
                )
            ),
            "About Qt",
        )
        about_qt.clicked.connect(self._show_about_qt)
        button_layout.addWidget(about_qt)
        button_layout.addStretch()
        ok_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_layout.addWidget(ok_button)
        ok_button.accepted.connect(self.accept)
        self.lo.addLayout(button_layout, 0)

        self.setWindowTitle("About")

    def _create_main_tab(self):
        tab = QWidget()
        lo = QVBoxLayout(tab)

        about_paragraph = dedent("""
        A custom Minecraft Launcher focused on speed & stability.<br>
        <br>
        (Not affiliated with Mojang Studios or Microsoft Corporation)
        <hr>
        <a
        href="https://github.com/ryderX86/PymLauncher"
        >https://github.com/ryderX86/PymLauncher</a>
        <hr>
        Copyright &#169;2026, Ryder Maddox (ryderX86)
        """)

        lo.addWidget(al(QLabel(about_paragraph, openExternalLinks=True)))

        self.tab_widget.addTab(tab, "About")

    def _create_acknowledgements_tab(self):
        tab = QWidget()
        lo = QVBoxLayout(tab)

        l_file = QFile(":/acknowledgements.md")
        if not l_file.open(QFile.OpenModeFlag.ReadOnly):
            log.warning("Device not open!")
        l_bytes = l_file.readAll().data()
        if isinstance(l_bytes, memoryview):
            l_bytes = l_bytes.tobytes()

        txt = l_bytes.decode("utf-8")
        text_view = QTextBrowser(openExternalLinks=True)
        text_view.setMarkdown(txt)
        lo.addWidget(text_view)
        self.tab_widget.addTab(tab, "Acknowledgements")

    @classmethod
    def create_show(cls):
        win = cls()
        win.exec()
        return

    @Slot()
    def _show_about_qt(self):
        QMessageBox.aboutQt(self, "About Qt")
