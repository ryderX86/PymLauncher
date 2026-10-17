from collections.abc import Generator
import glob
import json
import logging
import os
import sys

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from launcher import lifecycle, paths
from launcher.front.icon_helpers import ico_mgr
from launcher.front.styles import dark_theme_active

# noinspection unused-imports
from .custom_theme_support import BaseTheme, BuiltinTheme, CustomTheme

log = logging.getLogger(__name__)

_THEME_UI_NAMES = {
    "windows11": "Windows 11",
    "Windows": "Windows Classic",
    "windowsvista": "Windows Vista",
}


def get_widgets_themes_and_qstyles() -> Generator[tuple[str, str]]:
    themes_in = QStyleFactory.keys()
    for theme in themes_in:
        if theme in _THEME_UI_NAMES:
            yield _THEME_UI_NAMES[theme], theme
            continue
        yield theme, theme


def get_builtin_theme_objects_iter() -> Generator[BuiltinTheme]:
    for display, name in get_widgets_themes_and_qstyles():
        yield BuiltinTheme(display, name, name)


def get_builtin_theme_objects():
    return list(get_builtin_theme_objects_iter())


def get_custom_themes_iter():
    basedir = paths.themes
    for dirname in glob.iglob("**/", root_dir=basedir):
        dir_ = os.path.join(basedir, dirname)
        if not os.path.isdir(dir_):
            log.warning("Not a directory: %r", dir_)
            continue

        theme_json_f = os.path.join(dir_, "theme.json")
        if not os.path.isfile(theme_json_f):
            continue
        with open(theme_json_f, "rb") as file:
            try:
                theme_json = json.load(file)
            except json.JSONDecodeError as err:
                log.warning(
                    "Failed to decode theme.json file at %r:",
                    theme_json_f,
                    exc_info=err,
                )
                continue
        theme_css_f = os.path.join(dir_, "themeStyle.css")
        if os.path.isfile(theme_css_f):
            with open(theme_css_f, "r") as file:
                css = file.read()
        else:
            css = None
        try:
            theme = CustomTheme(theme_json, dir_, css)
        except Exception as err:
            log.warning("Failed to load theme from %r:", dir_, exc_info=err)
            continue
        else:
            yield theme


def get_custom_themes():
    return list(get_custom_themes_iter())


class _ThemeManager:
    __slots__ = ("_themes", "_default_theme", "_current_theme")
    _themes: dict[str, BaseTheme]
    _default_theme: BuiltinTheme
    _current_theme: BaseTheme

    def __init__(self):
        self._themes = {}

    def load(self):
        themes: list[BuiltinTheme] = [*get_builtin_theme_objects_iter()]
        if sys.platform == "linux":
            # workaround for windows classic showing up first for some reason??
            themes.sort(key=lambda t: 1 if t.id.lower().startswith("w") else 0)
        for i, theme in enumerate(themes):
            self._themes[theme.id] = theme
            if i == 0:
                theme.name = f"{theme.name} (default)"
                self._default_theme = theme
        for theme in get_custom_themes_iter():
            self._themes[theme.id] = theme

        self._current_theme = self._default_theme

    def set_theme(self, id_: str):
        if id_ == "default":
            id_ = self._default_theme.id
        if id_ not in self._themes:
            raise KeyError(f"{id_!r} not in themes")
        previous_was_dark_theme = dark_theme_active()
        self._current_theme = self._themes[id_]

        # workaround for the weird palette that qt tries to give when a theme
        # doesn't have one
        if self._current_theme.palette:
            QApplication.setStyle(self._current_theme.widgets)
            QApplication.setPalette(self._current_theme.palette)
        else:
            QApplication.setStyle(self._current_theme.widgets)
            QApplication.setPalette(QPalette())
        lifecycle.qapp.setStyleSheet(self._current_theme.qss or "")
        new_is_dark_theme = dark_theme_active()

        if previous_was_dark_theme != new_is_dark_theme:
            ico_mgr.refresh_color_scheme()

    def theme_list_tuple_iter(self):
        for theme in self._themes.values():
            yield theme.name, theme

    @property
    def current(self) -> BaseTheme:
        return self._current_theme


theme_manager = _ThemeManager()
