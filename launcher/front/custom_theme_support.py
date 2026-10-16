from dataclasses import asdict, dataclass, fields
from enum import StrEnum
import logging
import os
import re
import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyle, QStyleFactory

from launcher import lifecycle
from launcher.functions.text import camal_to_snake

if sys.platform == "win32":
    from .qstyle_overrides import Win11StyleOverrides

log = logging.getLogger(__name__)

_URL_RE = r"(url\()((theme:)|(\./))([^)\r\n;]+)(\))"
_URL_RE_COMPILED: re.Pattern | None = None


class CustomThemeManager:
    def __init__(self): ...


def blend_colors(base: QColor, overlay: QColor, fade_amount: float, add: bool):
    if add:
        base_red = base.red()
        base_blue = base.blue()
        base_green = base.green()
    else:
        base_red = int(base.red() * (1.0 - fade_amount))
        base_blue = int(base.blue() * (1.0 - fade_amount))
        base_green = int(base.green() * (1.0 - fade_amount))

    overlay_red = int(overlay.red() * fade_amount)
    overlay_blue = int(overlay.blue() * fade_amount)
    overlay_green = int(overlay.green() * fade_amount)

    return QColor(
        min(abs(base_red + overlay_red), 255),
        min(abs(overlay_green + base_green), 255),
        min(abs(overlay_blue + base_blue), 255),
        255,
    )


@dataclass(slots=True)
class ThemeColors:
    alternate_base: str | None = None
    base: str | None = None
    bright_text: str | None = None
    button: str | None = None
    button_text: str | None = None
    highlight: str | None = None
    highlighted_text: str | None = None
    link: str | None = None
    text: str | None = None
    tool_tip_base: str | None = None
    tool_tip_text: str | None = None
    window: str | None = None
    window_text: str | None = None
    fade_amount: float | None = None
    fade_color: str | None = None

    def __bool__(self):
        return any(bool(v) for v in asdict(self).values())

    def to_palette(self):
        p = QPalette()
        if self.alternate_base:
            p.setColor(QPalette.ColorRole.AlternateBase, self.alternate_base)
        if self.base:
            p.setColor(QPalette.ColorRole.Base, self.base)
        if self.bright_text:
            p.setColor(QPalette.ColorRole.BrightText, self.bright_text)
        if self.button:
            p.setColor(QPalette.ColorRole.Button, self.button)
        if self.button_text:
            p.setColor(QPalette.ColorRole.ButtonText, self.button_text)
        if self.highlight:
            p.setColor(QPalette.ColorRole.Highlight, self.highlight)
        if self.highlighted_text:
            p.setColor(
                QPalette.ColorRole.HighlightedText, self.highlighted_text
            )
        if self.link:
            p.setColor(QPalette.ColorRole.Link, self.link)
        if self.text:
            p.setColor(QPalette.ColorRole.Text, self.text)
        if self.tool_tip_base:
            p.setColor(QPalette.ColorRole.ToolTipBase, self.tool_tip_base)
        if self.tool_tip_text:
            p.setColor(QPalette.ColorRole.ToolTipText, self.tool_tip_text)
        if self.window:
            p.setColor(QPalette.ColorRole.Window, self.window)
        if self.window_text:
            p.setColor(QPalette.ColorRole.WindowText, self.window_text)
        if self.fade_amount and self.fade_color:
            overlay = QColor(self.fade_color)
            for color_role in QPalette.ColorRole:
                if color_role is QPalette.ColorRole.NColorRoles:
                    continue
                norm_color = p.color(color_role)
                overlay_disabled = blend_colors(
                    norm_color, overlay, self.fade_amount, False
                )
                p.setColor(
                    QPalette.ColorGroup.Disabled, color_role, overlay_disabled
                )
                p.setColor(
                    QPalette.ColorGroup.Inactive, color_role, norm_color
                )
        return p

    @classmethod
    def fields(cls):
        fields_out = []
        for field in fields(cls):
            fields_out.append(field.name)
        return fields_out

    @classmethod
    def iter_fields(cls):
        for field in fields(cls):
            yield field.name


class BaseTheme:
    __slots__ = ("name", "_widgets_name", "_widgets", "id")

    def __init__(self, name: str, widgets: str, id_: str):
        self._widgets_name = widgets
        self._widgets = None
        self.name = name
        self.id = id_

    @property
    def qss(self) -> str | None:
        return None

    @qss.setter
    def qss(self, new: str):
        raise NotImplementedError

    @property
    def widgets(self):
        return QStyleFactory.create(self._widgets_name)

    @property
    def palette(self) -> QPalette | None:
        return None

    @palette.deleter
    def palette(self):
        return None


class BuiltinTheme(BaseTheme):
    """Subclass for handling proxy styles for builtins"""

    def regenerate_style(self):
        del self._widgets
        if sys.platform == "win32" and self._widgets_name == "windows11":
            # pylint: disable-next=possibly-used-before-assignment
            assert Win11StyleOverrides  # type: ignore
            self._widgets = Win11StyleOverrides(
                QStyleFactory.create(self._widgets_name)
            )
        else:
            self._widgets = QStyleFactory.create(self._widgets_name)

    if sys.platform == "win32":

        def __init__(self, name: str, widgets: str):
            super().__init__(name, widgets, widgets)
            if widgets == "windows11":
                assert Win11StyleOverrides  # type: ignore
                self._widgets = Win11StyleOverrides(widgets)
                self._widgets.setParent(lifecycle)

        @property
        def widgets(self):
            if self._widgets_name == "windows11":
                assert Win11StyleOverrides  # type: ignore
                return Win11StyleOverrides(
                    QStyleFactory.create(self._widgets_name)
                )
            return super().widgets


class CustomTheme(BaseTheme):
    class Type(StrEnum):
        PRISM = "prism"
        PALETTE = "paletteOnly"
        PYM = "pym"

    __slots__ = (
        "_palette",
        "_qss",
        "_root_dir",
        "colors",
        "description",
    )
    _widgets_name: str
    name: str
    colors: ThemeColors
    _palette: QPalette | None
    _widgets: QStyle | None

    def __init__(
        self,
        theme_json: dict,
        root_dir: str,
        qss: str | None = None,
    ):
        w: str | None = theme_json.get("widgets")
        if w:
            self._widgets_name = w
        else:
            self._widgets_name = QStyleFactory.keys()[0]
        super().__init__(theme_json["name"], self._widgets_name, root_dir)
        colors: dict = theme_json.get("colors", {})
        self._palette = None
        self._widgets = None
        field_names = ThemeColors.fields()
        if colors:
            new_json = {}
            for key, value in colors.items():
                new_key = camal_to_snake(key)
                if new_key not in field_names:
                    log.warning(
                        "Unrecognized key %r in theme %r",
                        new_key,
                        theme_json["name"],
                    )
                    continue
                new_json[new_key] = value
            self.colors = ThemeColors(**new_json)
        else:
            self.colors = ThemeColors()
        self._root_dir = root_dir
        if self._root_dir and qss:
            self._qss = self.process_qss(qss)
        elif qss:
            log.warning("Cannot use QSS without a root directory set!")

    @property
    def _get_qss_resources_directory(self):
        if not self._root_dir:
            raise RuntimeError(
                "Cannot get resources directory without a root dir set"
            )
        return os.path.join(self._root_dir, "resources")

    def process_qss(self, qss: str):
        global _URL_RE_COMPILED
        res = f"{self._get_qss_resources_directory.rstrip("/")}/"
        if sys.platform == "win32":
            res = res.replace("\\", "/")
        qq = any(a in res for a in " \r\n\t()")
        if not _URL_RE_COMPILED:
            _URL_RE_COMPILED = re.compile(_URL_RE)
        for match in _URL_RE_COMPILED.finditer(qss):
            url_call: str = match[0]
            scheme = match[2]
            if scheme:
                if qq:
                    url_call = url_call.replace(scheme, f'"{res}')
                    url_call = url_call.replace(match[5], f'{match[5]}"')
                else:
                    url_call = url_call.replace(scheme, res)
            elif not qq:
                url_call = url_call.replace("url(", f"url({res}")
            else:
                url_call = url_call.replace("url(", f'url("{res}')
                url_call = f'{url_call[:-1]}")'
            qss = qss.replace(match[0], url_call)
        return qss

    @property
    def qss(self):
        return self._qss

    @qss.setter
    def qss(self, new: str):
        self._qss = self.process_qss(new)

    @property
    def palette(self):
        if self._palette:
            return self._palette
        elif not self.colors:
            return None
        return self.colors.to_palette()

    @palette.deleter
    def palette(self):
        del self._palette
