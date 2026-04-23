"""
QSS stylesheet
"""
from colorsys import rgb_to_hsv, hsv_to_rgb

from PySide6.QtGui import QFont

from minecraftlauncher.front.rgb import hex_to_rgb, rgb_to_hex

# Colors
BG_DARKEST = "#111111"
BG_DARK = "#181818"
BG_SURFACE = "#1e1e1e"
BG_SURFACE_LIGHT = "#252525"
BG_INPUT = "#202020"

ACCENT_LIGHTER = "#90C481"
ACCENT_LIGHT = "#69B452"
ACCENT_HOVER = "#4EA235"
ACCENT = "#3A971E"
ACCENT_PRESS = "#34881B"
ACCENT_DIM = "#2f7b18"

TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#a0a0a0"
TEXT_MUTED = "#707070"

BORDER = "#2c2c2c"
BORDER_LIGHT = "#3a3a3a"

DANGER = "#e74c3c"
DANGER_HOVER = "#c0392b"

def mk_accent_hover(r: float, g: float, b: float):
    h, s, v = rgb_to_hsv(r, g, b)
    s = max(s * 0.95, 0)
    v = min(v * 1.1, 1)
    nr, ng, nb = hsv_to_rgb(h, s, v)
    return rgb_to_hex(nr, ng, nb)

def mk_accent_light(r: float, g: float, b: float):
    h, s, v = rgb_to_hsv(r, g, b)
    s = max(s * 0.9, 0)
    v = min(v * 1.15, 1)
    nr, ng, nb = hsv_to_rgb(h, s, v)
    return rgb_to_hex(nr, ng, nb)

def mk_accent_lighter(r: float, g: float, b: float):
    h, s, v = rgb_to_hsv(r, g, b)
    s = max(s * 0.8, 0)
    v = min(v * 1.25, 1)
    nr, ng, nb = hsv_to_rgb(h, s, v)
    return rgb_to_hex(nr, ng, nb)

def mk_accent_press(r: float, g: float, b: float):
    h, s, v = rgb_to_hsv(r, g, b)
    s = min(v * 1.25, 1)
    v = max(s * 0.75, 0)
    nr, ng, nb = hsv_to_rgb(h, s, v)
    return rgb_to_hex(nr, ng, nb)

def mk_accent_dim(r: float, g: float, b: float):
    h, s, v = rgb_to_hsv(r, g, b)
    s = min(v * 1.33, 1)
    v = max(s * 0.77, 0)
    nr, ng, nb = hsv_to_rgb(h, s, v)
    return rgb_to_hex(nr, ng, nb)

def compile_colors(**kwargs):
    bg_darkest = kwargs.get("bg_darkest", BG_DARKEST).strip("#")
    bg_dark = kwargs.get("bg_dark", BG_DARK).strip("#")
    bg_surface = kwargs.get("bg_surface", BG_SURFACE).strip("#")
    bg_surface_light = kwargs.get(
        "bg_surface_light", BG_SURFACE_LIGHT).strip("#")
    bg_input = kwargs.get("bg_input", BG_INPUT).strip("#")
    
    accent = kwargs.get("accent", ACCENT).strip("#")
    if accent != ACCENT:
        r, g, b = hex_to_rgb(accent)
        accent_lighter = mk_accent_lighter(r, g, b)
        print(accent_lighter)
        accent_light = mk_accent_light(r, g, b)
        print(accent_light)
        accent_hover = mk_accent_hover(r, g, b)
        print(accent_hover)
        accent_press = mk_accent_press(r, g, b)
        print(accent_press)
        accent_dim = mk_accent_dim(r, g, b)
        print(accent_dim)
    else:
        accent_lighter = ACCENT_LIGHTER.strip("#")
        accent_light = ACCENT_LIGHT.strip("#")
        accent_hover = ACCENT_HOVER.strip("#")
        accent_press = ACCENT_PRESS.strip("#")
        accent_dim = ACCENT_DIM.strip("#")
    
    text_primary = kwargs.get("text_primary", TEXT_PRIMARY).strip("#")
    text_secondary = kwargs.get("text_secondary", TEXT_SECONDARY).strip("#")
    text_muted = kwargs.get("text_muted", TEXT_MUTED).strip("#")

    border = kwargs.get("border", BORDER).strip("#")
    border_light = kwargs.get("border_light", BORDER_LIGHT).strip("#")

    danger = kwargs.get("danger", DANGER).strip("#")
    danger_hover = kwargs.get("danger_hover", DANGER_HOVER).strip("#")

    return {
        "BG_DARKEST": "#" + bg_darkest,
        "BG_DARK": "#" + bg_dark,
        "BG_SURFACE": "#" + bg_surface,
        "BG_SURFACE_LIGHT": "#" + bg_surface_light,
        "BG_INPUT": "#" + bg_input,

        "ACCENT": "#" + accent,
        "ACCENT_LIGHTER": "#" + accent_lighter,
        "ACCENT_LIGHT": "#" + accent_light,
        "ACCENT_HOVER": "#" + accent_hover,
        "ACCENT_PRESS": "#" + accent_press,
        "ACCENT_DIM": "#" + accent_dim,

        "TEXT_PRIMARY": "#" + text_primary,
        "TEXT_SECONDARY": "#" + text_secondary,
        "TEXT_MUTED": "#" + text_muted,
        "BORDER": "#" + border,
        "BORDER_LIGHT": "#" + border_light,
        "DANGER": "#" + danger,
        "DANGER_HOVER": "#" + danger_hover
    }

template = """
/* Main */
QWidget {{
    background-color: {BG_DARKEST};
    color: {TEXT_PRIMARY};
}}
QWidget[sidebar="true"] {{
    background-color: {BG_SURFACE};
}}
QWidget[surface="true"],
QWidget[surface="true"] QWidget,
QWidget[surface="true"] QLabel {{
    background-color: {BG_SURFACE};
    border-radius: 5px;
}}

/* Window */
QMainWindow {{
    background-color: {BG_DARKEST};
}}

/* Labels */
QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: none;
}}
QLabel[secondary="true"] {{
    color: {TEXT_SECONDARY};
}}
QLabel[heading="true"] {{
    font-size: 20px;
    font-weight: 700;
    color: {ACCENT};
    margin-bottom: 4px;
}}
QLabel[h2="true"] {{
    font-size: 16px;
    font-weight: 700;
    color: {ACCENT};
    margin-left: 4px;
}}
QLabel[subheading="true"] {{
    font-size: 14px;
    color: {TEXT_SECONDARY};
}}
QLabel[section="true"] {{
    font-size: 14px;
    font-weight: 700;
}}

/* Interactive */
QPushButton {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {BG_SURFACE_LIGHT};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {BG_DARK};
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}
QPushButton:disabled {{
    background-color: {BG_DARK};
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}

QPushButton[mini="true"] {{
    padding: 4px 9px;
    font-weight: 400;
}}

QPushButton[accent="true"] {{
    background-color: {ACCENT};
    color: #111111;
    border: none;
}}
QPushButton[accent="true"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[accent="true"]:pressed {{
    background-color: {ACCENT_PRESS};
}}
QPushButton[accent="true"]:disabled {{
    background-color: {ACCENT_DIM};
}}

QPushButton[play="true"] {{
    background-color: {ACCENT};
    color: {TEXT_PRIMARY};
    border: none;
    font-size: 18px;
    font-weight: 700;
    border-radius: 8px;
    padding: 12px 32px;
}}
QPushButton[play="true"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[play="true"]:pressed {{
    background-color: {ACCENT_PRESS};
}}

QPushButton[danger="true"] {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {DANGER};
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER};
    color: white;
}}

QPushButton[danger="true"] {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {DANGER};
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER};
    color: white;
}}

QPushButton[nav="true"] {{
    background: none;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: 0;
    padding: 14px 20px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton[nav="true"]:hover {{
    background: {BG_SURFACE_LIGHT};
    color: {TEXT_PRIMARY};
}}
QPushButton[nav="true"]:pressed {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
}}
QPushButton[nav="true"][active="true"] {{
    background: {BG_SURFACE_LIGHT};
    color: {ACCENT};
    border-left: 3px solid {ACCENT};
}}

QRadioButton::indicator::unchecked {{
    image: url(:/icon/symbol/circle.svg);
}}
QRadioButton::indicator::checked {{
    image: url(:/icon/symbol/circle-fill.svg);
}}

QMenu {{
    icon-size: 16px;
    padding: 4px;
    background-color: {BG_SURFACE};
    background-clip: border;
    border: 1px solid {BORDER};
}}
QMenu::item {{
    background-color: transparent;
    padding: 4px 6px;
    border-radius: 4px;
}}
QMenu::icon {{
    top: 1px;
    left: 4px;
}}
QMenu::item:selected {{
    background-color: {BG_SURFACE_LIGHT};
}}
QMenu::item:disabled {{
    color: {TEXT_MUTED};
}}

QCheckBox::indicator {{
    width: 1em;
    height: 1em;
}}
QCheckBox::indicator::unchecked {{
    image: url(:/icon/symbol/square.svg);
}}
QCheckBox::indicator:checked {{
    image: url(:/icon/symbol/checkbox-checked.svg);
}}
QCheckBox::indicator:pressed {{
    image: url(:/icon/symbol/square-filled.svg);
}}
QCheckBox::indicator:indeterminate {{
    image: url(:/icon/symbol/square-half.svg);
}}

/* Input */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: {ACCENT_DIM};
    min-height: 22px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}

/* Combo box */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 22px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: url(":/icon/symbol/dropdown.svg");
    color: {TEXT_PRIMARY};
    background-clip: content;
    width: 12px;
    height: 12px;
    margin-right: 8px;
}}
QComboBox::down-arrow:on {{
    image: url(":/icon/symbol/dropdown-up.svg");
}}
QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    selection-background-color: {ACCENT_DIM};
    outline: 0;
}}
QComboBox ::item:selected {{
    background-color: {ACCENT_DIM};
    color: {TEXT_PRIMARY};
}}

QComboBox[compact="true"] {{
    padding: 4px 12px;
    min-height: 1em;
    max-height: 1em;
}}

QComboBox[icons_only="true"] ::item {{
    height: 56px;
}}

QComboBox[bigIcons="true"] ::item {{
    min-height: 48px;
    icon-size: 32px;
    padding: 0 12px;
    margin: 2px 0;
}}
QComboBox[bigIcons="true"] ::item:selected {{
    background-color: {ACCENT_DIM};
    color: {TEXT_PRIMARY};
    margin: 0 0;
    padding-top: 2px;
}}
QComboBox[bigIcons="true"] QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    selection-background-color: {ACCENT_DIM};
    outline: 0;
}}

/* Spinner */
QSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
}}

/* Progress bar */
QProgressBar {{
    background-color: {BG_DARK};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    color: {TEXT_PRIMARY};
    height: 20px;
}}
QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_DIM}, stop:1 {ACCENT}
    );
    border-radius: 5px;
}}

/* Scrollbar */
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 10px;
    border: none;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 10px;
    border: none;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* Lists */
QListView[profiles="true"] {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
    padding: 4px;
}}
QListView[profiles="true"]::item {{
    padding: 0 12px;
    height: 3em;
    border-radius: 4px;
    margin: 2px 0;
}}
QListView[profiles="true"]::item:selected {{
    background-color: {ACCENT};
}}
QListView[profiles="true"]::item:hover {{
    background-color: {BG_SURFACE_LIGHT};
}}
QListView[profiles="true"]::item:hover:selected {{
    background-color: {ACCENT_PRESS};
}}
QListView[profiles="true"]::item:disabled {{
    background-color: {BG_SURFACE_LIGHT};
    color: {TEXT_MUTED};
}}
QListView[profiles="true"]::item:hover:disabled {{
    background-color: {ACCENT_PRESS};
}}

QListWidget[icons="true"]::item, QListView[icons="true"]::item {{
    padding: 2px 2px;
}}

QListWidget[icons="true"]::item::icon, QListView[icons="true"]::item::icon {{
    margin-top: 4px;
    margin-bottom: 4px;
}}

/* Tab */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {BG_SURFACE};
}}
QTabBar::tab {{
    background: {BG_DARK};
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {BG_SURFACE};
    color: {ACCENT};
}}

/* Group */
QGroupBox {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 6px;
    color: {ACCENT};
}}

/* Tooltips */
QToolTip {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* Status Bar */
QStatusBar {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
}}

/* Separator/frame */
QFrame[frameShape="4"] {{
    background-color: {BORDER};
    max-height: 1px;
    border: none;
}}
QFrame[frameShape="5"] {{
    background-color: {BORDER};
    max-width: 1px;
    border: none;
}}

/* Dialog */
QDialog {{
    background-color: {BG_DARKEST};
}}
"""

def regen_styles(): return template.format(**globals())

STYLESHEET = regen_styles()

FONT = QFont()
FONT.setFamilies(["Segoe UI", "Inter", "Roboto", "sans-serif"])
FONT.setPointSize(10)

uses_dark_mode = True