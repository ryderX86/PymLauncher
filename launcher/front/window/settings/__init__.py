from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from launcher import JarRedownloadBehavior, config, constants, lifecycle, paths
from launcher.front.qt.binding_mixin import BindingMixin
from launcher.front.qt.widget_mapping_adapter import WidgetMappingAdapter
from launcher.front.qt.widgets import TooltipHint
from launcher.front.theming import theme_manager
from launcher.front.theming.icon_helpers import (
    IconName,
    get_icon,
    icon_theme_manager,
)
from launcher.functions import Suppressable, popup_folder


def make_setting(label: str, widget: QWidget, *widgets: QWidget):
    lo = QHBoxLayout()
    qlabel = QLabel(label)
    lo.addWidget(qlabel)
    lo.addWidget(widget, 1)
    for widget in widgets:
        lo.addWidget(widget, 0)

    return lo


@Slot()
def _open_icons_folder():
    popup_folder(paths.icon_themes)


@Slot()
def _open_themes_folder():
    popup_folder(paths.themes)


class SettingsWindow(BindingMixin, QDialog):
    _sections: list[QGroupBox]
    _mappers: set[WidgetMappingAdapter]

    _instance: SettingsWindow | None = None
    _initialized: bool
    _dirty: bool

    class SettingsPage(QWidget):
        def __init__(self, name: str, icon: QIcon | None = None, parent=None):
            super().__init__(parent=parent)
            self.icon = icon
            self.name = name
            self.list_item = QListWidgetItem()
            self.list_item.setText(self.name)
            if self.icon:
                self.list_item.setIcon(self.icon)

            self._sections = []

            self.lo = QVBoxLayout()
            self.setLayout(self.lo)

        def add_section(self, name: str):
            section = QGroupBox(name)
            self.lo.addWidget(section, 0)
            self._sections.append(section)
            lo = QVBoxLayout()
            section.setLayout(lo)
            return lo

        def section(self, idx: int):
            if idx > len(self._sections):
                raise IndexError("Index outside of range")
            return self._sections[idx]

        def add_widget(self, w: QWidget):
            self.lo.addWidget(w, 0)

        def remove_widget(self, w: QWidget):
            self.lo.removeWidget(w)

        def add_layout(self, l: QLayout):
            self.lo.addLayout(l, 0)

        def remove_layout(self, l: QLayout):
            self.lo.removeItem(l)

    def __new__(cls, *args, **kwargs):
        if cls._instance is not None:
            return cls._instance
        new = super().__new__(cls, *args, **kwargs)
        new._initialized = False
        cls._instance = new
        return new

    def __init__(self, parent=None):
        if self._initialized:
            return
        self._initialized = True
        super().__init__(parent=parent)
        self._mappers = set()

        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

        self._layout.setContentsMargins(4, 4, 4, 4)

        self._main_lo = QHBoxLayout()
        self._layout.addLayout(self._main_lo, 1)

        self.tabs_list = QListWidget(
            supportedDragActions=Qt.DropAction.IgnoreAction
        )
        self.tabs_list.setFixedWidth(150)
        self._main_lo.addWidget(self.tabs_list, 0)

        self.main = QStackedLayout()
        self._main_lo.addLayout(self.main, 1)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self._buttons = QDialogButtonBox(
            standardButtons=(
                QDialogButtonBox.StandardButton.Apply
                | QDialogButtonBox.StandardButton.Cancel  # type: ignore
                | QDialogButtonBox.StandardButton.Ok  # type: ignore
            )
        )
        self._layout.addWidget(self._buttons, 0)

        self._make_general_page()
        self._make_connectivity_page()
        self._make_appearance_page()

        self.tabs_list.currentRowChanged.connect(self.main.setCurrentIndex)
        self.setMinimumHeight(500)

    def bind(self):
        self._dirty = False
        with self._on_val_change.suppressed():
            for adapter in self._mappers:
                adapter.signal.connect(self._on_val_change)
                adapter.reset_known(config)
                adapter.reset()

        self._buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).clicked.connect(self._on_ok)
        self._buttons.button(
            QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._do_save)
        self._buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        ).clicked.connect(self.reject)
        self.rejected.connect(self.reset)
        self.tabs_list.setCurrentRow(0)
        self._buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(
            False
        )

    @Slot()
    def reset(self):
        with self._on_val_change.suppressed():
            for adapter in self._mappers:
                adapter.reset()
        self._on_val_change()

    @Slot()
    @Slot(object)
    @Suppressable
    def _on_val_change(self, *_):
        self._dirty = False
        for adapter in self._mappers:
            if adapter.changed():
                self._dirty = True
                break

        self._buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(
            self._dirty
        )

    @Slot()
    def _do_save(self):
        if not self._dirty:
            return
        with self._on_val_change.suppressed():
            for adapter in self._mappers:
                setattr(
                    config,
                    adapter.attr_name,
                    adapter.normalize(adapter.read()),
                )
                adapter.reset_known(config)
            config.save()
        self._on_val_change()
        lifecycle.config_updated.emit()
        # let the appearance setting updates take effect:
        QApplication.processEvents()
        return

    @Slot()
    def _on_ok(self):
        self._do_save()
        self.accept()

    def _make_general_page(self):
        general = self.SettingsPage("General")

        # behavior section
        behavior = general.add_section("Behavior")
        after_game_opens = QComboBox()
        after_game_opens.addItem(
            "Keep launcher open", config.PostLaunchBehavior.KEEP_OPEN
        )
        after_game_opens.addItem(
            "Hide launcher until game closes", config.PostLaunchBehavior.HIDE
        )
        after_game_opens.addItem(
            "Close launcher if game doesn't crash",
            config.PostLaunchBehavior.CLOSE_WHEN_DONE,
        )
        after_game_opens.addItem(
            "Close launcher", config.PostLaunchBehavior.CLOSE
        )
        self._mappers.add(
            WidgetMappingAdapter(
                normalize=config.PostLaunchBehavior,
                widget=after_game_opens,
                read=after_game_opens.currentData,
                write=after_game_opens.setCurrentIndex,
                attr_name="post_launch_option",
                signal=after_game_opens.currentIndexChanged,
            )
        )
        behavior.addLayout(
            make_setting("After Minecraft opens:", after_game_opens), 0
        )

        use_device_codes = QCheckBox("Use device code flow for logins")
        udc_final = TooltipHint.widget_tooltip(
            "Use an external web browser from another device (i.e., "
            "your phone) to log in instead of using a webview window or"
            " default browser.",
            use_device_codes,
        )
        self._mappers.add(
            WidgetMappingAdapter(
                read=use_device_codes.isChecked,
                write=use_device_codes.setChecked,
                attr_name="use_device_code_for_logins",
                signal=use_device_codes.checkStateChanged,
                widget=use_device_codes,
            )
        )
        behavior.addWidget(udc_final, 0)

        always_show_debug = QCheckBox(
            "Always show debug options when right-clicking"
        )
        asd_final = TooltipHint.widget_tooltip(
            "When holding shift and right-clicking on a supported item, "
            "debug options may show up. This option allows those debug options to "
            "always be visible when right-clicking.",
            always_show_debug,
        )
        self._mappers.add(
            WidgetMappingAdapter(
                read=always_show_debug.isChecked,
                write=always_show_debug.setChecked,
                attr_name="always_show_debug_options",
                signal=always_show_debug.checkStateChanged,
                widget=always_show_debug,
            )
        )
        behavior.addWidget(asd_final, 0)

        self._copy_login_code = QCheckBox(
            "Copy device login code to clipboard"
        )
        use_device_codes.checkStateChanged.connect(
            self._use_device_codes_changed
        )

        # visual section
        visual = general.add_section("Visual Behavior")

        show_tooltip_icons = QCheckBox("Show Tooltip Icons")
        visual.addWidget(show_tooltip_icons, 0)
        self._mappers.add(
            WidgetMappingAdapter(
                read=show_tooltip_icons.isChecked,
                write=show_tooltip_icons.setChecked,
                attr_name="tooltip_icons_enabled",
                signal=show_tooltip_icons.checkStateChanged,
                widget=show_tooltip_icons,
            )
        )

        home_page_logs = QCheckBox("Show game logs on home page")
        hpl_final = TooltipHint.widget_tooltip(
            "Show the game's console logs on the home screen.\n"
            "(Could use a lot of CPU resources!)",
            home_page_logs,
        )
        visual.addWidget(hpl_final, 0)
        self._mappers.add(
            WidgetMappingAdapter(
                read=home_page_logs.isChecked,
                write=home_page_logs.setChecked,
                attr_name="show_logs_on_home",
                signal=home_page_logs.checkStateChanged,
                widget=home_page_logs,
            )
        )

        self.home_log_fmt = QLineEdit(
            placeholderText=constants.DEFAULT_LOG_TEMPLATE,
            clearButtonEnabled=True,
        )
        hplf_final = TooltipHint.widget_tooltip(
            "Accepted formats:<ul>"
            "<li><code>%(name)s</code></li>"
            "<li><code>{name}</code></li></ul>"
            "Valid variable names:<ul>"
            "<li><code>logger</code></li>"
            "<li><code>timestamp</code></li>"
            "<li><code>level</code></li>"
            "<li><code>thread</code></li>"
            "<li><code>message</code></li></ul>",
            self.home_log_fmt,
        )
        visual.addWidget(hplf_final, 0)
        self._mappers.add(
            WidgetMappingAdapter(
                read=self.home_log_fmt.text,
                write=self.home_log_fmt.setText,
                attr_name="logging_template",
                signal=self.home_log_fmt.textEdited,
                widget=self.home_log_fmt,
                normalize=lambda t: (
                    t if t != constants.DEFAULT_LOG_TEMPLATE else None
                ),
            )
        )

        general.lo.addStretch()

        self.tabs_list.addItem(general.list_item)
        self.main.addWidget(general)

    def _make_connectivity_page(self):
        connectivity = self.SettingsPage("Connectivity")

        # downloads section
        downloads = connectivity.add_section("Downloads")

        self.file_redownload = QComboBox()
        self.file_redownload.addItem(
            "Always redownload (default)",
            JarRedownloadBehavior.REDOWNLOAD,
        )
        self.file_redownload.addItem(
            "Redownload once (not recommended)",
            JarRedownloadBehavior.REDOWNLOAD_ONCE,
        )
        self.file_redownload.addItem(
            "Never re-download (not recommended)",
            JarRedownloadBehavior.NEVER,
        )
        self._mappers.add(
            WidgetMappingAdapter(
                normalize=JarRedownloadBehavior,
                read=self.file_redownload.currentData,
                write=self._set_redownload,  # type: ignore
                attr_name="redownload_option",
                signal=self.file_redownload.currentIndexChanged,
            )
        )
        downloads.addLayout(
            make_setting(
                "When a file doesn't have a hash:", self.file_redownload
            ),
            0,
        )

        self.disable_lzma = QCheckBox("Disable downloading with LZMA")
        self._mappers.add(
            WidgetMappingAdapter(
                read=self.disable_lzma.isChecked,
                write=self.disable_lzma.setChecked,
                attr_name="disable_lzma_downloads",
                signal=self.disable_lzma.checkStateChanged,
                widget=self.disable_lzma,
            )
        )
        downloads.addWidget(
            TooltipHint.widget_tooltip(
                "Disables LZMA compression on downloads that enable it (such "
                "as Mojang-provided Java installations), allowing downloads to"
                " be less CPU-intensive, by using more internet "
                "bandwidth instead. Most of the Minecraft installation doesn't"
                " use LZMA compression though, so this option may be "
                "inconsequential if you have a decently modern system.",
                self.disable_lzma,
            )
        )

        connectivity.lo.addStretch()

        self.tabs_list.addItem(connectivity.list_item)
        self.main.addWidget(connectivity)

    def _make_appearance_page(self):
        appearance = self.SettingsPage("Appearance")
        theme = appearance.add_section("Theme")

        self.theme_selector = QComboBox()
        open_themes_folder = QPushButton(
            get_icon(IconName.OPEN_FOLDER), "Open Folder"
        )
        open_themes_folder.clicked.connect(_open_themes_folder)
        theme.addLayout(
            make_setting("Theme:", self.theme_selector, open_themes_folder)
        )
        for idx, (name, data) in enumerate(
            theme_manager.theme_list_tuple_iter()
        ):
            self.theme_selector.addItem(name, data)
            self.theme_selector.setItemData(idx, data.id, 256)
        self._mappers.add(
            WidgetMappingAdapter(
                normalize=lambda t: t.name if not isinstance(t, str) else t,
                read=self.theme_selector.currentData,
                write=self._set_theme_selector,
                attr_name="theme",
                signal=self.theme_selector.currentIndexChanged,
                widget=self.theme_selector,
            )
        )

        self.icon_theme_selector = QComboBox()
        open_icons_folder = QPushButton(
            get_icon(IconName.OPEN_FOLDER), "Open Folder"
        )
        open_icons_folder.clicked.connect(_open_icons_folder)
        theme.addLayout(
            make_setting("Icons:", self.icon_theme_selector, open_icons_folder)
        )
        for name, id_ in icon_theme_manager.selector_themes:
            self.icon_theme_selector.addItem(name, id_)
        self._mappers.add(
            WidgetMappingAdapter(
                read=self.icon_theme_selector.currentData,
                write=self._set_icon_theme_selector,
                attr_name="icon_theme",
                signal=self.icon_theme_selector.currentIndexChanged,
                widget=self.icon_theme_selector,
            )
        )

        appearance.lo.addStretch(1)

        self.tabs_list.addItem(appearance.list_item)
        self.main.addWidget(appearance)

    def _set_theme_selector(self, data):
        idx = self.theme_selector.findData(
            data, flags=Qt.MatchFlag.MatchExactly, role=256
        )
        if idx >= 0:
            self.theme_selector.setCurrentIndex(idx)
            return
        self.theme_selector.setCurrentIndex(0)

    def _set_icon_theme_selector(self, data):
        idx = self.icon_theme_selector.findData(
            data, flags=Qt.MatchFlag.MatchExactly
        )
        if idx >= 0:
            self.icon_theme_selector.setCurrentIndex(idx)
            return
        self.icon_theme_selector.setCurrentIndex(0)

    def _use_device_codes_changed(self, state: Qt.CheckState):
        self._copy_login_code.setEnabled(bool(state.value))

    def _set_redownload(self, o: JarRedownloadBehavior):
        match o:
            case o.REDOWNLOAD:
                self.file_redownload.setCurrentIndex(0)
            case o.REDOWNLOAD_ONCE:
                self.file_redownload.setCurrentIndex(1)
            case o.NEVER:
                self.file_redownload.setCurrentIndex(2)

    def _on_home_logs_checked(self, state: Qt.CheckState):
        match state:
            case Qt.CheckState.Checked | Qt.CheckState.PartiallyChecked:
                self.home_log_fmt.setText(config.logging_template)
                self.home_log_fmt.setEnabled(True)
            case _:
                self.home_log_fmt.setText("")
                self.home_log_fmt.setEnabled(False)
