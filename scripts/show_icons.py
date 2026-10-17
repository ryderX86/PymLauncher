import sys

from PySide6.QtCore import QMutex, QPoint, QRect, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QStyleFactory,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)
import win32gui


def dll_ico_count(dll: str):
    return win32gui.ExtractIconEx("shell32.dll", -1, 0)


def shell32_qicon(dll: str, idx: int):
    largeh, smallh = win32gui.ExtractIconEx(dll, idx, 1)

    if not largeh and not smallh:
        return QIcon()

    try:
        ico = QIcon()
        if largeh:
            qimgl = QImage.fromHICON(int(largeh[0]))
            ico.addPixmap(QPixmap.fromImage(qimgl))
        if smallh:
            qimgs = QImage.fromHICON(int(smallh[0]))
            ico.addPixmap(QPixmap.fromImage(qimgs))
        return ico
    finally:
        for h in largeh:
            win32gui.DestroyIcon(h)
        for h in smallh:
            win32gui.DestroyIcon(h)


qapp = QApplication()

qapp.setApplicationName("Icon list")

check_icons = [
    "address-book-new",
    "application-exit",
    "appointment-new",
    "call-start",
    "call-stop",
    "contact-new",
    "document-new",
    "document-open",
    "document-open-recent",
    "document-page-setup",
    "document-print",
    "document-print-preview",
    "document-properties",
    "document-revert",
    "document-save",
    "document-save-as",
    "document-send",
    "edit-clear",
    "edit-copy",
    "edit-cut",
    "edit-delete",
    "edit-find",
    "edit-find-replace",
    "edit-paste",
    "edit-redo",
    "edit-select-all",
    "edit-undo",
    "find-location",
    "folder-new",
    "format-indent-less",
    "format-indent-more",
    "format-justify-center",
    "format-justify-fill",
    "format-justify-left",
    "format-justify-right",
    "format-text-direction-ltr",
    "format-text-direction-rtl",
    "format-text-bold",
    "format-text-italic",
    "format-text-underline",
    "format-text-strikethrough",
    "go-bottom",
    "go-down",
    "go-first",
    "go-home",
    "go-jump",
    "go-last",
    "go-next",
    "go-previous",
    "go-top",
    "go-up",
    "help-about",
    "help-contents",
    "help-faq",
    "insert-image",
    "insert-link",
    "insert-object",
    "insert-text",
    "list-add",
    "list-remove",
    "mail-forward",
    "mail-mark-important",
    "mail-mark-junk",
    "mail-mark-notjunk",
    "mail-mark-read",
    "mail-mark-unread",
    "mail-message-new",
    "mail-reply-all",
    "mail-reply-sender",
    "mail-send",
    "mail-send-receive",
    "media-eject",
    "media-playback-pause",
    "media-playback-start",
    "media-playback-stop",
    "media-record",
    "media-seek-backward",
    "media-seek-forward",
    "media-skip-backward",
    "media-skip-forward",
    "object-flip-horizontal",
    "object-flip-vertical",
    "object-rotate-left",
    "object-rotate-right",
    "process-stop",
    "system-lock-screen",
    "system-log-out",
    "system-run",
    "system-search",
    "system-reboot",
    "system-shutdown",
    "tools-check-spelling",
    "view-fullscreen",
    "view-refresh",
    "view-restore",
    "view-sort-ascending",
    "view-sort-descending",
    "window-close",
    "window-new",
    "zoom-fit-best",
    "zoom-in",
    "zoom-original",
    "zoom-out",
    "process-working",
    "accessories-calculator",
    "accessories-character-map",
    "accessories-dictionary",
    "accessories-screenshot-tool",
    "accessories-text-editor",
    "help-browser",
    "multimedia-volume-control",
    "preferences-desktop-accessibility",
    "preferences-desktop-font",
    "preferences-desktop-keyboard",
    "preferences-desktop-locale",
    "preferences-desktop-multimedia",
    "preferences-desktop-screensaver",
    "preferences-desktop-theme",
    "preferences-desktop-wallpaper",
    "system-file-manager",
    "system-software-install",
    "system-software-update",
    "utilities-system-monitor",
    "utilities-terminal",
    "applications-accessories",
    "applications-development",
    "applications-engineering",
    "applications-games",
    "applications-graphics",
    "applications-internet",
    "applications-multimedia",
    "applications-office",
    "applications-other",
    "applications-science",
    "applications-system",
    "applications-utilities",
    "preferences-desktop",
    "preferences-desktop-peripherals",
    "preferences-desktop-personal",
    "preferences-other",
    "preferences-system",
    "preferences-system-network",
    "system-help",
    "audio-card",
    "audio-input-microphone",
    "battery",
    "camera-photo",
    "camera-video",
    "camera-web",
    "computer",
    "drive-harddisk",
    "drive-optical",
    "drive-removable-media",
    "input-gaming",
    "input-keyboard",
    "input-mouse",
    "input-tablet",
    "media-flash",
    "media-floppy",
    "media-optical",
    "media-tape",
    "modem",
    "multimedia-player",
    "network-wired",
    "network-wireless",
    "pda",
    "phone",
    "printer",
    "scanner",
    "video-display",
    "emblem-default",
    "emblem-documents",
    "emblem-downloads",
    "emblem-favorite",
    "emblem-important",
    "emblem-mail",
    "emblem-photos",
    "emblem-readonly",
    "emblem-shared",
    "emblem-symbolic-link",
    "emblem-synchronized",
    "emblem-system",
    "emblem-unreadable",
    "application-x-executable",
    "audio-x-generic",
    "font-x-generic",
    "image-x-generic",
    "package-x-generic",
    "text-html",
    "text-x-generic",
    "text-x-generic-template",
    "text-x-script",
    "video-x-generic",
    "x-office-address-book",
    "x-office-calendar",
    "x-office-document",
    "x-office-presentation",
    "x-office-spreadsheet",
    "folder",
    "folder-remote",
    "network-server",
    "network-workgroup",
    "start-here",
    "user-bookmarks",
    "user-desktop",
    "user-home",
    "user-trash",
    "appointment-missed",
    "appointment-soon",
    "audio-volume-high",
    "audio-volume-low",
    "audio-volume-medium",
    "audio-volume-muted",
    "battery-caution",
    "battery-low",
    "dialog-error",
    "dialog-information",
    "dialog-password",
    "dialog-question",
    "dialog-warning",
    "folder-drag-accept",
    "folder-open",
    "folder-visiting",
    "image-loading",
    "image-missing",
    "mail-attachment",
    "mail-unread",
    "mail-read",
    "mail-replied",
    "mail-signed",
    "mail-signed-verified",
    "media-playlist-repeat",
    "media-playlist-shuffle",
    "network-error",
    "network-idle",
    "network-offline",
    "network-receive",
    "network-transmit",
    "network-transmit-receive",
    "printer-error",
    "printer-printing",
    "security-high",
    "security-medium",
    "security-low",
    "software-update-available",
    "software-update-urgent",
    "sync-error",
    "sync-synchronizing",
    "task-due",
    "task-past-due",
    "user-available",
    "user-away",
    "user-idle",
    "user-offline",
    "user-trash-full",
    "weather-clear",
    "weather-clear-night",
    "weather-few-clouds",
    "weather-few-clouds-night",
    "weather-fog",
    "weather-overcast",
    "weather-severe-alert",
    "weather-showers",
    "weather-showers-scattered",
    "weather-snow",
    "weather-storm",
]


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=-1, hSpacing=-1, vSpacing=-1):
        super().__init__(parent)
        self._hSpace = hSpacing
        self._vSpace = vSpacing
        self._item_list = []
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def horizontalSpacing(self):
        if self._hSpace >= 0:
            return self._hSpace
        return self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._vSpace >= 0:
            return self._vSpace
        return self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    def doLayout(self, rect, testOnly):
        x, y, line_height = rect.x(), rect.y(), 0

        for item in self._item_list:
            space_x = self.horizontalSpacing()
            space_y = self.verticalSpacing()

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            assert isinstance(parent, QWidget)
            return parent.style().pixelMetric(pm, None, parent)
        else:
            assert isinstance(parent, QLayout)
            return parent.spacing()


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.w = QWidget()
        self.setCentralWidget(self.w)
        self.lo = QVBoxLayout()
        self.w.setLayout(self.lo)
        self._buttons: dict[
            str | QStyle.StandardPixmap | QIcon.ThemeIcon | int, QPushButton
        ] = {}

        self._theme_box = QComboBox()
        for theme in QStyleFactory.keys():
            self._theme_box.addItem(theme)
        self._theme_box.setCurrentIndex(0)
        self._theme_box.currentTextChanged.connect(self._change_style)

        self._size_box = QSpinBox()
        self._size_box.setValue(
            qapp.style().pixelMetric(QStyle.PixelMetric.PM_ButtonIconSize)
        )
        self._size_box.valueChanged.connect(
            self._change_icon_size, Qt.ConnectionType.DirectConnection
        )

        lo = QHBoxLayout()
        lo.addWidget(QLabel("Style:"), 0)
        lo.addWidget(self._theme_box, 0)
        lo.addWidget(QLabel("Size:"))
        lo.addWidget(self._size_box)
        self.lo.addLayout(lo)

        lo2 = QHBoxLayout()
        self.search = QLineEdit()
        self.search.textChanged.connect(self._filter)
        lo2.addWidget(QLabel("Search:"))
        lo2.addWidget(self.search)
        self.lo.addLayout(lo2)

        self.scroll_area = QScrollArea()
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_lo = QVBoxLayout()
        self.scroll_widget.setLayout(self.scroll_lo)

        self.scroll_lo.addWidget(QLabel("QIcon.ThemeIcon:"), 0)
        self.icon_flow = FlowLayout()
        for member in sorted(
            (member for member in QIcon.ThemeIcon), key=lambda m: m.name
        ):
            button = QPushButton(QIcon.fromTheme(member), member.name)
            if button.icon().isNull():
                button.setDisabled(True)
            self._buttons[member] = button
            self.icon_flow.addWidget(button)
        for name in sorted(check_icons):
            button = QPushButton(QIcon.fromTheme(name), name)
            if button.icon().isNull():
                button.setDisabled(True)
            self._buttons[name] = button
            self.icon_flow.addWidget(button)
        self.scroll_lo.addLayout(self.icon_flow)

        self.scroll_lo.addWidget(QLabel("QStyle.StandardPixmap:"), 0)
        self.pixmap_flow = FlowLayout()
        for member in sorted(
            (member for member in qapp.style().StandardPixmap),
            key=lambda m: m.value,
        ):
            button = QPushButton(
                qapp.style().standardIcon(member), member.name
            )
            if button.icon().isNull():
                button.setDisabled(True)
            self._buttons[member] = button
            self.pixmap_flow.addWidget(button)
        self.scroll_lo.addLayout(self.pixmap_flow, 0)

        if sys.platform == "win32":
            self.shell32_flow = FlowLayout()
            self.scroll_lo.addWidget(QLabel("Shell32:"), 0)
            for i in range(0, dll_ico_count("shell32.dll") + 1):
                ico = shell32_qicon("shell32.dll", i)
                if ico.isNull():
                    continue
                button = QPushButton(ico, str(i))
                self._buttons[f"DLLshell32{i}"] = button
                self.shell32_flow.addWidget(button)
            self.scroll_lo.addLayout(self.shell32_flow, 0)

            self.imgres_flow = FlowLayout()
            self.scroll_lo.addWidget(QLabel("imageres:"), 0)
            for i in range(0, dll_ico_count("imageres.dll") + 1):
                ico = shell32_qicon("imageres.dll", i)
                if ico.isNull():
                    continue
                button = QPushButton(ico, str(i))
                self._buttons[f"DLLimageres{i}"] = button
                self.imgres_flow.addWidget(button)
            self.scroll_lo.addLayout(self.imgres_flow, 0)

        self.scroll_area.setWidget(self.scroll_widget)
        self.lo.addWidget(self.scroll_area)
        self.setMinimumWidth(720)
        self._icon_change_mutex = QMutex()

    def _change_style(self, style_name: str):
        style = QStyleFactory.create(style_name)
        qapp.setStyle(style)
        for icon_type, button in self._buttons.items():
            match icon_type:
                case QStyle.StandardPixmap():
                    button.setIcon(qapp.style().standardIcon(icon_type))
                case QIcon.ThemeIcon() | str():
                    button.setIcon(QIcon.fromTheme(icon_type))

    def _change_icon_size(self, size: int):
        for icon_name_type, button in self._buttons.items():
            button.setIconSize(QSize(size, size))
            style_opt = QStyleOption().initFrom(button)
            if isinstance(icon_name_type, QStyle.StandardPixmap):
                button.setIcon(
                    qapp.style().standardIcon(
                        icon_name_type, style_opt, button
                    )
                )

    def _filter(self, text: str):
        t = text.lower()
        if not t:
            for button in self._buttons.values():
                button.setHidden(False)
            return
        for button in self._buttons.values():
            if t not in button.text().lower():
                button.setHidden(True)
            else:
                button.setHidden(False)


if __name__ == "__main__":
    win = MainWindow()
    win.show()
    qapp.exec()
