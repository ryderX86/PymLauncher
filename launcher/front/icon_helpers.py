"""Messy module, should probably be split into multiple."""

from collections.abc import Iterable
from enum import IntEnum, StrEnum, auto
from functools import cached_property
import os
from typing import NamedTuple
import configparser
import logging
import sys

from PySide6.QtCore import (
    QDir,
    QDirListing,
    QFile,
    QRect,
    QResource,
    QSize,
)
from PySide6.QtGui import (
    QFontDatabase,
    QIcon,
    QIconEngine,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QAbstractButton, QApplication, QStyle

from launcher.front.styles import dark_theme_active

_log = logging.getLogger(__name__)
db = QFontDatabase()


class Icon(NamedTuple):
    qicon: QIcon.ThemeIcon | str | QStyle.StandardPixmap
    prism: str
    win32: str
    fallback: str
    name: IconName


class IconThemeType(IntEnum):
    QT = 0
    PRISM = 1
    WIN32 = 2
    FREEDESKTOP = 3


def _refresh_all_icons():  # TODO: handle other widgets
    for w in QApplication.allWidgets():
        match w:
            case QAbstractButton():
                ico = w.icon()
                name = ico.name()
                if not name.startswith("ADAPTING_"):
                    continue
                i = IconName(name[9:])
                w.setIcon(get_icon(i))


class IconTheme:
    _themes: dict[str, IconTheme] = {}
    log = _log.getChild("IconTheme")

    def __init__(
        self,
        display_name: str,
        actual_name: str,
        index_dir: str | None,
        type_: IconThemeType,
        inherit_from: str | None = None,
        pairing: str | None = None,
        color_scheme: bool | None = None,
    ):
        self.display_name = display_name
        self.id = actual_name
        self.type = type_
        self._inherits = inherit_from
        self._pair = pairing
        self.uses_dark_icons = color_scheme
        match self.type:
            case IconThemeType.FREEDESKTOP | IconThemeType.PRISM:
                if not index_dir:
                    raise RuntimeError(
                        "Cannot create Pym/Prism theme without including the index file"
                    )
                self.index_file = f"{index_dir}/index.theme"
                self.directory = index_dir
            case _:
                self.index_file = None
                self.directory = None

    @property
    def inherits(self):
        return self._inherits

    @inherits.setter
    def inherits(self, new_val: str | None):
        self._inherits = new_val

    def _info(self, message: str, *args):
        base_msg = f"{self.id}: {message}"
        self.log.info(base_msg, *args)

    def _warn(self, message: str, *args):
        base_msg = f"{self.id}: {message}"
        self.log.warning(base_msg, *args)

    def _debug(self, message: str, *args):
        base_msg = f"{self.id}: {message}"
        self.log.debug(base_msg, *args)

    @property
    def exists(self):
        # use QFile since the built-in QResource themes also use this class
        match self.type:
            case IconThemeType.FREEDESKTOP | IconThemeType.PRISM:
                assert self.index_file is not None
                return QFile(self.index_file).exists()
            case IconThemeType.WIN32:
                return db.hasFamily(self.id)
            case IconThemeType.QT:
                # really no way to check, have to assume it's fine and
                # fall back to default if it's not
                return True

    @property
    def pairname(self):
        return self._pair

    @pairname.setter
    def pairname(self, new: str | None):
        if new == self._pair:
            return
        elif new and new != self._pair:
            self._warn("New pair set, this could go badly.")
            self._pair = new
        elif not new:
            self._pair = None

    @classmethod
    def load_system_icon_font(cls, display_name, name: str):
        if not db.hasFamily(name):
            cls.log.debug("Couldn't find font family for %r", name)
            return
        return IconTheme(
            display_name,
            name,
            None,
            IconThemeType.WIN32,
            None,
        )

    if sys.platform == "win32":

        @classmethod
        def get_system_fonts(cls):  # type: ignore
            _SYSICON_FONTS = {
                "Windows 11": "Segoe Fluent Icons",
                "Windows 10": "Segoe MDL2 Assets",
                "Windows 8": "Segoe UI Symbol",
            }
            for displayname, themeid in _SYSICON_FONTS.items():
                yield cls.load_system_icon_font(displayname, themeid)

    else:

        @classmethod
        def get_system_fonts(cls) -> Iterable[IconTheme]:
            return tuple()


default_qt = IconTheme(
    "System (no theme)",
    "",
    None,
    IconThemeType.QT,
    "",
)


class ThemePair(NamedTuple):
    light: IconTheme
    dark: IconTheme


class IconThemeManager:
    FALLBACK_PATH_DARK = QIcon.fallbackSearchPaths()
    FALLBACK_PATH_DARK.append(":/icons/fallback/dark")
    FALLBACK_PATH_LIGHT = QIcon.fallbackSearchPaths()
    FALLBACK_PATH_LIGHT.append(":/icons/fallback/light")
    _search_paths: list[str] = QIcon.themeSearchPaths()
    if sys.platform == "linux":
        _search_paths.extend(
            {
                os.path.expanduser("~/.local/share/icons"),
                os.path.expanduser("~/.icons"),
                "/usr/share/icons",
                "/usr/share/pixmaps",
            }
        )
        FALLBACK_PATH_DARK.append("/usr/share/icons/hicolor/")
        FALLBACK_PATH_LIGHT.append("/usr/share/icons/hicolor/")
    _themes: dict[str, IconTheme]
    _paired_themes: dict[str, ThemePair]
    _system_themes: dict[str, IconTheme]
    _current: IconTheme
    _fallback: IconTheme | None
    _has_system_themes: bool
    _default: IconTheme

    def __init__(self):
        self._themes = {"": default_qt}
        self._paired_themes = {}
        self._system_themes = {}
        self._current = default_qt
        self._fallback = None
        self._has_system_themes = False

    @classmethod
    def add_search_path(cls, path: str):
        cls._search_paths.append(path)
        cls.reset_search_paths()

    @classmethod
    def reset_search_paths(cls):
        QIcon.setThemeSearchPaths(cls._search_paths)

    def iter_themes(self):
        for pairid, (light, _) in self._paired_themes.items():
            yield pairid, light
        for id_, theme in self._themes.items():
            yield theme, id_

    def has_theme(self, id_: str):
        if id_ in self._themes or id_ in self._paired_themes:
            return True
        else:
            # pylint: disable-next=unbalanced-dict-unpacking
            for light, dark in self._paired_themes.values():
                if light.id == id_ or dark.id == id_:
                    return True
        return False

    def get_theme(self, new: str):
        if new in self._themes:
            return self._themes[new]
        elif new in self._paired_themes:
            if dark_theme_active():
                idx = 0
            else:
                idx = 1
            return self._paired_themes[new][idx]
        else:
            _log.warning("Couldn't find theme %r, falling back to Qt", new)
            return default_qt

    def set_theme(self, new: str):
        if new == "\x00":
            # hacky workaround for default themes varying between systems
            if self._default.pairname:
                return self.set_theme(self._default.pairname)
            return self.set_theme(self._default.id)
        if self._current.id == new:
            refresh = True
        else:
            refresh = False
        self._current = self.get_theme(new)
        if self._current.inherits and self.has_theme(self._current.inherits):
            self._fallback = self.get_theme(self._current.inherits)
        if refresh:
            QIcon.setThemeName("")
            if self._fallback:
                QIcon.setFallbackThemeName(self._fallback.id)
            QApplication.processEvents()
            self.reset_search_paths()
        QIcon.setThemeName(self._current.id)
        if self._fallback:
            QIcon.setFallbackThemeName(self._fallback.id)
        else:
            QIcon.setFallbackThemeName("")
        if dark_theme_active():
            QIcon.setFallbackSearchPaths(self.FALLBACK_PATH_LIGHT)
        else:
            QIcon.setFallbackSearchPaths(self.FALLBACK_PATH_DARK)
        self.reset_search_paths()
        _refresh_all_icons()

    def load_themes(self):
        prev_fonts = self._themes
        self._themes = {}
        for font in IconTheme.get_system_fonts():
            self._has_system_themes = True
            self._themes[font.id] = font
            self._system_themes[font.id] = font
        self._themes.update(prev_fonts)
        for id_, theme in self._themes.items():
            if not theme.exists:
                del self._themes[id_]
        pairs: dict[str, tuple] = {}
        for parent in QIcon.themeSearchPaths():
            if parent.startswith(":/"):
                continue
            l = QDirListing(parent, QDirListing.IteratorFlag.DirsOnly)
            for d in l:  # type: ignore
                directory = d.value().filePath()
                qdir = QDir(directory)
                index = QFile(qdir.filePath("index.theme"))
                if index.exists():
                    if index.open(QFile.OpenModeFlag.ReadOnly):
                        data = index.readAll().data()
                        index.close()
                    else:
                        _log.warning(
                            "Couldn't read theme index in %r: %s",
                            qdir.absolutePath(),
                            index.errorString(),
                        )
                        continue
                elif (
                    index := QResource(qdir.filePath("index.theme"))
                ).isFile() and index.isValid():
                    data = index.uncompressedData().data()
                else:
                    continue

                if isinstance(data, memoryview):
                    data = data.tobytes()
                parser = configparser.ConfigParser(interpolation=None)
                try:
                    parser.read_string(data.decode())
                except configparser.Error as err:
                    _log.warning(
                        "Failed to parse icon theme in %r:",
                        qdir.absolutePath(),
                        exc_info=err,
                    )
                    continue

                if not parser.has_section("Icon Theme"):
                    _log.warning(
                        "Invalid index file in %r", qdir.absolutePath()
                    )
                    continue

                theme_id = parser.get(
                    "Icon Theme", "Name", fallback=directory.split("/")[-1]
                )

                if (
                    parser.get("Icon Theme", "Type", fallback="").lower()
                    == "pym"
                ):
                    display_name = parser.get(
                        "Icon Theme", "DisplayName", fallback=theme_id
                    )
                    theme_type = IconThemeType.FREEDESKTOP
                    pairing = parser.get("Icon Theme", "PairId", fallback=None)
                    raw_color_scheme = parser.get(
                        "Icon Theme", "ColorScheme", fallback=""
                    )
                    match raw_color_scheme.lower():
                        case "light":
                            is_dark = False
                        case "dark":
                            is_dark = True
                        case "":
                            is_dark = None
                        case _:
                            _log.warning(
                                "Invalid icon scheme: %r", raw_color_scheme
                            )
                            is_dark = None
                else:
                    display_name = parser.get(
                        "Icon Theme", "Name", fallback=theme_id
                    )
                    theme_type = IconThemeType.PRISM
                    pairing = None
                    is_dark = None

                inherits_from = parser.get(
                    "Icon Theme", "Inherits", fallback=None
                )

                if theme_id in self._themes:
                    self._themes.pop(theme_id)
                theme = IconTheme(
                    display_name,
                    theme_id,
                    directory,
                    theme_type,
                    inherits_from,
                    pairing,
                    is_dark,
                )
                if not theme.pairname:
                    self._themes[theme_id] = theme
                elif theme.pairname in pairs:
                    other = pairs[theme.pairname][0]
                    if theme.uses_dark_icons:
                        nt = (other, theme)
                    else:
                        nt = (theme, other)
                    pairs[theme.pairname] = nt
                else:
                    pairs[theme.pairname] = (theme,)
        for pairid, (light, dark) in pairs.items():
            self._paired_themes[pairid] = ThemePair(light, dark)

        renamed_default = False
        for theme in self._system_themes.values():
            _log.debug("default theme: %r", theme.display_name)
            theme.display_name = f"{theme.display_name} (default)"
            renamed_default = True
            self._default = theme
            break
        if not renamed_default:
            # pylint: disable-next=unbalanced-dict-unpacking
            for light, dark in self._paired_themes.values():
                _log.debug(
                    "default theme: %r (& %r)",
                    light.display_name,
                    dark.display_name,
                )
                light.display_name = f"{light.display_name} (default)"
                dark.display_name = f"{dark.display_name} (default)"
                renamed_default = True
                self._default = light
                break
        if not renamed_default:
            for theme in self._themes.values():
                _log.debug("default theme: %r", theme.display_name)
                theme.display_name = f"{theme.display_name} (default)"
                self._default = theme
                break

    @property
    def current(self):
        return self._current

    @property
    def fallback(self):
        return self._fallback

    def refresh_color_scheme(self):
        need_dark_icons = dark_theme_active()
        if need_dark_icons:
            QIcon.setFallbackSearchPaths(self.FALLBACK_PATH_DARK)
        else:
            QIcon.setFallbackSearchPaths(self.FALLBACK_PATH_LIGHT)
        if self._current.uses_dark_icons == need_dark_icons:
            return None
        if self.current.pairname:
            return self.set_theme(self.current.pairname)
        return self.set_theme(self.current.id)

    @property
    def selector_themes(self):
        for id_, theme in self._themes.items():
            yield theme.display_name, id_
        for id_, (light, _) in self._paired_themes.items():
            yield light.display_name, id_
        return

    @cached_property
    def default(self) -> str:
        for theme in self._system_themes.values():
            return theme.id
        for theme in self._paired_themes.values():
            t = theme[0]
            assert t.pairname is not None
            return theme[0].pairname  # type: ignore
        for theme in self._themes.values():
            return theme.id
        return default_qt.id


ico_mgr = IconThemeManager()


class IconName(StrEnum):
    SETTINGS = auto()
    UTILITY = auto()
    INSTALLER = auto()
    DATA_FOLDER = auto()
    CHANGE_SKIN = auto()
    HELP = auto()
    HELP_ABOUT = auto()
    DUPLICATE = auto()
    CANCEL = auto()
    CUT = auto()
    COPY = auto()
    SAVE = auto()
    SAVE_AS = auto()
    EXPORT = auto()
    DELETE = auto()
    SORT = auto()
    SORT_CUSTOM = auto()
    ACCOUNT_ADD = auto()
    ACCOUNT_REMOVE = auto()
    ACCOUNT_REFRESH = auto()
    REFRESH = auto()
    SYNC = auto()
    REPAIR = auto()
    OPEN_FOLDER = auto()
    FOLDER = auto()
    OPEN_IMAGE = auto()
    IMAGE = auto()
    APPLICATION = auto()
    TERMINAL = auto()
    UNDO = auto()
    REDO = auto()
    IMPORT = auto()
    CHECK_UPDATES = auto()
    PERSONALIZE = auto()
    CONNECTIVITY = auto()
    CONNECTED = auto()
    NOT_CONNECTED = auto()
    EDIT = auto()
    RENAME = auto()
    EDIT_LABEL = RENAME
    ADD = auto()
    REMOVE = auto()
    TOOLTIP = auto()
    RESET = auto()


_ICONMAPPINGS: dict[IconName, Icon] = {
    IconName.SETTINGS: Icon(
        "preferences-system",
        "settings",
        "\ue713",
        "settings",
        IconName.SETTINGS,
    ),
    IconName.UTILITY: Icon(
        "applications-development",
        "externaltools",
        "\uec7a",
        "tools",
        IconName.UTILITY,
    ),
    IconName.INSTALLER: Icon(
        "window-new",
        "checkupdate",
        "\uebd3",
        "cloud-download",
        IconName.INSTALLER,
    ),
    IconName.DATA_FOLDER: Icon(
        "drive-harddisk",
        "viewfolder",
        "\ue838",
        "folder-symlink",
        IconName.DATA_FOLDER,
    ),
    IconName.CHANGE_SKIN: Icon(
        QIcon.ThemeIcon.CameraWeb, "", "\ue898", "", IconName.CHANGE_SKIN
    ),
    IconName.HELP: Icon(
        "help-browser", "help", "\ue897", "missing", IconName.HELP
    ),
    IconName.HELP_ABOUT: Icon(
        QIcon.ThemeIcon.HelpAbout,
        "about",
        "\ue946",
        "info",
        IconName.HELP_ABOUT,
    ),
    IconName.DUPLICATE: Icon(
        QIcon.ThemeIcon.EditCopy, "copy", "\uf413", "copy", IconName.DUPLICATE
    ),
    IconName.CANCEL: Icon(
        "process-stop", "", "\ue711", "cancel", IconName.CANCEL
    ),
    IconName.CUT: Icon(
        QIcon.ThemeIcon.EditCut, "cut", "\ue8c6", "cut", IconName.CUT
    ),
    IconName.COPY: Icon(
        QIcon.ThemeIcon.EditCopy, "copy", "\ue8c8", "copy", IconName.COPY
    ),
    IconName.SAVE: Icon(
        QIcon.ThemeIcon.DocumentSave,
        "save",
        "\ue74e",
        "save",
        IconName.SAVE,
    ),
    IconName.SAVE_AS: Icon(
        QIcon.ThemeIcon.DocumentSaveAs,
        "save",
        "\ue792",
        "save",
        IconName.SAVE_AS,
    ),
    IconName.EXPORT: Icon(
        QIcon.ThemeIcon.DocumentSend,
        "export",
        "\uede1",
        "share",
        IconName.EXPORT,
    ),
    IconName.DELETE: Icon(
        QIcon.ThemeIcon.EditDelete,
        "delete",
        "\ue74d",
        "trash",
        IconName.DELETE,
    ),
    IconName.SORT: Icon(
        (
            "view-sort-ascending"
            if sys.platform != "win32"
            else "format-justify-left"
        ),
        "sort",
        "\ue8cb",
        "dropdown",
        IconName.SORT,
    ),
    IconName.SORT_CUSTOM: Icon(
        "user-bookmarks",
        "sort",
        "\ue8fd",
        "font",
        IconName.SORT_CUSTOM,
    ),
    IconName.ACCOUNT_ADD: Icon(
        QIcon.ThemeIcon.ContactNew,
        "new",
        "\ue8fa",
        "profile-add",
        IconName.ACCOUNT_ADD,
    ),
    IconName.ACCOUNT_REFRESH: Icon(
        QIcon.ThemeIcon.SyncSynchronizing,
        "",
        "\ue895",
        "refresh",
        IconName.ACCOUNT_REFRESH,
    ),
    IconName.ACCOUNT_REMOVE: Icon(
        "system-log-out",
        "remove",
        "\ue8f8",
        "profile-remove",
        IconName.ACCOUNT_REMOVE,
    ),
    IconName.REFRESH: Icon(
        QIcon.ThemeIcon.ViewRefresh,
        "refresh",
        "\ue72c",
        "refresh",
        IconName.REFRESH,
    ),
    IconName.SYNC: Icon(
        QIcon.ThemeIcon.SyncSynchronizing,
        "sync",
        "\ue8f8",
        "refresh",
        IconName.SYNC,
    ),
    IconName.REPAIR: Icon(
        QIcon.ThemeIcon.DocumentProperties,
        "repair",
        "\ue90f",
        "repair",
        IconName.REPAIR,
    ),
    IconName.OPEN_FOLDER: Icon(
        QIcon.ThemeIcon.FolderOpen,
        "viewfolder",
        "\ue838",
        "folder-symlink",
        IconName.OPEN_FOLDER,
    ),
    IconName.FOLDER: Icon(
        "folder",
        "viewfolder",
        "\ue8b7",
        "folder",
        IconName.FOLDER,
    ),
    IconName.OPEN_IMAGE: Icon(
        QStyle.StandardPixmap.SP_FileLinkIcon,
        "",
        "\ue7c5",
        "images",
        IconName.OPEN_IMAGE,
    ),
    IconName.IMAGE: Icon(
        "emblem-photos", "", "\ue91b", "image", IconName.IMAGE
    ),
    IconName.APPLICATION: Icon(
        "application-x-executable", "java", "\ueb3b", "", IconName.APPLICATION
    ),
    IconName.TERMINAL: Icon(
        "utilities-terminal",
        "custom-commands",
        "\ue756",
        "code-slash",
        IconName.TERMINAL,
    ),
    IconName.UNDO: Icon(
        QIcon.ThemeIcon.EditUndo,
        "undo",
        "\ue7a7",
        "circle-counter-clockwise",
        IconName.UNDO,
    ),
    IconName.REDO: Icon(
        QIcon.ThemeIcon.EditRedo,
        "redo",
        "\ue7a6",
        "circle-clockwise",
        IconName.REDO,
    ),
    IconName.IMPORT: Icon(
        QIcon.ThemeIcon.DocumentOpen,
        "import",
        "\ue8b5",
        "import",
        IconName.IMPORT,
    ),
    IconName.CHECK_UPDATES: Icon(
        "system-software-update",
        "checkupdate",
        "\uecc5",
        "",
        IconName.CHECK_UPDATES,
    ),
    IconName.PERSONALIZE: Icon(
        "preferences-desktop-personal",
        "appearance",
        "\ue771",
        "",
        IconName.PERSONALIZE,
    ),
    IconName.CONNECTIVITY: Icon(
        QIcon.ThemeIcon.NetworkWired,
        "proxy",
        "\ue968",
        "",
        IconName.CONNECTIVITY,
    ),
    IconName.CONNECTED: Icon(
        QIcon.ThemeIcon.NetworkWired, "", "\uf0b9", "", IconName.CONNECTED
    ),
    IconName.NOT_CONNECTED: Icon(
        QIcon.ThemeIcon.NetworkOffline,
        "",
        "\uec9c",
        "",
        IconName.NOT_CONNECTED,
    ),
    IconName.EDIT: Icon(
        QIcon.ThemeIcon.MailMessageNew,
        "edit",
        "\ue70f",
        "edit",
        IconName.EDIT,
    ),
    IconName.RENAME: Icon(
        QIcon.ThemeIcon.MailMessageNew,
        "edit",
        "\uef60",
        "edit",
        IconName.RENAME,
    ),
    IconName.ADD: Icon(
        QIcon.ThemeIcon.ListAdd, "new", "\ue710", "add", IconName.ADD
    ),
    IconName.REMOVE: Icon(
        QIcon.ThemeIcon.ListRemove,
        "remove",
        "\ue738",
        "remove",
        IconName.REMOVE,
    ),
    IconName.TOOLTIP: Icon(
        "dialog-information",
        "about",
        "\ue82f",
        "tooltip",
        IconName.TOOLTIP,
    ),
    IconName.RESET: Icon(
        QIcon.ThemeIcon.ViewRestore,
        "refresh",
        "\ue845",
        "circle-counter-clockwise",
        IconName.RESET,
    ),
}


def _icon(name: str | IconName):
    if name not in IconName:
        raise ValueError(f"Bad icon name: {name}")
    if isinstance(name, IconName):
        return _ICONMAPPINGS[name]
    else:
        return _ICONMAPPINGS[IconName(name)]


class AdaptiveIconEngine(QIconEngine):
    # instance attributes
    _last_known_theme: IconTheme | None
    _last_known_fallback: IconTheme | None
    _last_icon: QIcon | None
    _is_null: bool

    log = logging.getLogger("AdaptiveIconEngine")

    def __init_subclass__(cls) -> None:
        cls.log = logging.getLogger(cls.__qualname__)
        return super().__init_subclass__()

    def __init__(self, ico: IconName | Icon):
        super().__init__()
        if isinstance(ico, IconName):
            ico = _ICONMAPPINGS[ico]
        self.icon = ico
        self._last_known_fallback = None
        self._last_known_theme = None
        self._last_icon = None
        self._get_qicon()

    def _get_qicon(self):
        icon_theme = ico_mgr.current
        fallback = ico_mgr.fallback
        if (
            icon_theme == self._last_known_theme
            and fallback == self._last_known_fallback
            and self._last_icon
        ):
            return self._last_icon
        self._last_known_theme = icon_theme
        self._last_known_fallback = fallback

        if isinstance(
            (res_ico := self.icon[icon_theme.type]), QStyle.StandardPixmap
        ):
            ico = QIcon(QApplication.style().standardIcon(res_ico))
        else:
            ico = QIcon.fromTheme(res_ico)
        if ico.isNull() and fallback:
            if isinstance(
                (res_fallback := self.icon[fallback.type]),
                QStyle.StandardPixmap,
            ):
                ico = QIcon(QApplication.style().standardIcon(res_fallback))
            else:
                ico = QIcon.fromTheme(res_fallback)
        if ico.isNull():
            self._is_null = True
            return QIcon()
        else:
            self._is_null = False
            self._last_icon = ico
            return ico

    def pixmap(
        self, size: QSize, mode: QIcon.Mode, state: QIcon.State
    ) -> QPixmap:
        return self._get_qicon().pixmap(size, mode, state)

    def isNull(self) -> bool:
        return self._is_null

    def availableSizes(
        self,
        /,
        mode: QIcon.Mode = QIcon.Mode.Normal,
        state: QIcon.State = QIcon.State.Off,
    ) -> list[QSize]:
        if self._last_icon:
            return self._last_icon.availableSizes(mode, state)
        return super().availableSizes(mode, state)

    def actualSize(
        self, size: QSize, mode: QIcon.Mode, state: QIcon.State
    ) -> QSize:
        if self._last_icon:
            return self._last_icon.actualSize(size, mode, state)
        return super().actualSize(size, mode, state)

    def clone(self):
        return AdaptiveIconEngine(self.icon)

    def iconName(self) -> str:
        return f"ADAPTING_{self.icon[-1]}"

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        if self.isNull():
            painter.end()
            return
        painter.save()
        painter.restore()
        pix = self.pixmap(rect.size(), mode, state)
        painter.drawPixmap(rect, pix)
        return


def get_icon(i: Icon | IconName):
    return QIcon(AdaptiveIconEngine(i))
