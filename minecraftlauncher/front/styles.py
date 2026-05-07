"""
QSS stylesheet
"""

import sys

from PySide6.QtGui import QFont, QFontInfo, QPalette, QColor

from minecraftlauncher.front.rgb import hex_to_rgbi
from minecraftlauncher import QAPP

CRole = QPalette.ColorRole
CGroup = QPalette.ColorGroup


def hex_to_qrgb(hex_: str):
    return QColor(*hex_to_rgbi(hex_))


PALETTE = QAPP.palette()


# Colors
BG_DARKEST = "#111111"
BG_DARK = "#181818"
BG_SURFACE = "#1e1e1e"
BG_INPUT = "#202020"
BG_SURFACE_LIGHT = "#252525"

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

PALETTE.setColor(CRole.WindowText, hex_to_qrgb(TEXT_PRIMARY))
PALETTE.setColor(CGroup.Disabled, CRole.WindowText, hex_to_qrgb(TEXT_MUTED))
PALETTE.setColor(CRole.ButtonText, hex_to_qrgb(TEXT_PRIMARY))
PALETTE.setColor(CGroup.Disabled, CRole.ButtonText, hex_to_qrgb(TEXT_MUTED))
PALETTE.setColor(CGroup.Active, CRole.ButtonText, hex_to_qrgb(TEXT_SECONDARY))
PALETTE.setColor(CRole.ToolTipText, hex_to_qrgb(TEXT_PRIMARY))
PALETTE.setColor(CRole.Window, hex_to_qrgb(BG_DARK))
PALETTE.setColor(CRole.Base, hex_to_qrgb(BG_DARK))
PALETTE.setColor(CRole.AlternateBase, hex_to_qrgb(BG_SURFACE))
PALETTE.setColor(CRole.Button, hex_to_qrgb(BG_SURFACE))
PALETTE.setColor(CRole.ToolTipBase, hex_to_qrgb(BG_SURFACE))
PALETTE.setColor(CRole.PlaceholderText, hex_to_qrgb(TEXT_MUTED))
PALETTE.setColor(CRole.Text, hex_to_qrgb(TEXT_PRIMARY))
PALETTE.setColor(CRole.Light, hex_to_qrgb(BG_INPUT))
PALETTE.setColor(CRole.Midlight, hex_to_qrgb(BG_SURFACE_LIGHT))
PALETTE.setColor(CRole.Mid, hex_to_qrgb(BG_DARKEST))

PALETTE.setColor(QPalette.ColorRole.Accent, hex_to_qrgb(ACCENT))


STYLESHEET = f"""
/* Main */
QWidget[surface="true"] {{
    background-color: palette(alternate-base);
}}
QWidget[border="true"] {{
    border: 1px solid palette(border);
}}

:focus {{
    outline: none;
}}

/* Window */
QMainWindow {{
    background-color: palette(mid);
}}

/* Labels */
QLabel[secondary="true"], SecondaryLabel {{
    color: {TEXT_SECONDARY};
}}
QLabel[heading="true"], h1, Header1 {{
    font-size: 20px;
    font-weight: 700;
    color: palette(accent);
    margin-bottom: 4px;
}}
QLabel[h2="true"], h2, Header2 {{
    font-size: 16px;
    font-weight: 700;
    color: palette(accent);
    margin-left: 4px;
}}
QLabel[subheading="true"], Subheading {{
    font-size: 14px;
    color: {TEXT_SECONDARY};
}}
QLabel[section="true"], SectionLabel {{
    font-size: 14px;
    font-weight: 700;
}}

/* Interactive */
QPushButton {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 9px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BG_SURFACE_LIGHT};
    border-color: {BORDER_LIGHT};
}}
QPushButton:pressed {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
}}
QPushButton:disabled {{
    background-color: {BG_DARK};
    color: {TEXT_MUTED};
}}

QPushButton[large="true"], LargeButton {{
    padding: 7px 18px;
}}

QPushButton[mini="true"], SmallButton {{
    padding: 4px 9px;
    font-weight: 400;
}}

QPushButton[accent="true"], AccentButton {{
    background-color: {ACCENT};
    color: #111111;
    border-color: {BORDER};
}}
QPushButton[accent="true"]:hover,
AccentButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[accent="true"]:pressed,
AccentButton:pressed {{
    background-color: {ACCENT_PRESS};
}}
QPushButton[accent="true"]:disabled,
AccentButton:disabled {{
    background-color: {ACCENT_DIM};
}}

QPushButton[play="true"], PlayButton {{
    border-color: {ACCENT};
    color: {TEXT_PRIMARY};
    padding: 12px 32px;
}}
QPushButton[play="true"]:hover,
PlayButton:hover {{
    border-color: {ACCENT_HOVER};
}}
QPushButton[play="true"]:pressed,
PlayButton:pressed {{
    border-color: {ACCENT_DIM};
}}

QPushButton[danger="true"] {{
    background-color: transparent;
    color: {DANGER};
    border: 1px solid {DANGER};
}}
QPushButton[danger="true"]:hover {{
    background-color: {DANGER_HOVER};
    color: white;
}}


QMenu {{
    icon-size: 16px;
    padding: 4px;
    background-color: {BG_SURFACE};
    background-clip: border;
    border: 1px solid {BORDER};
    border-radius: 1px;
}}
QMenu::item {{
    padding: 4px 6px;
    border-radius: 4px;
}}
QMenu::item[delete="true"], QMenu::item#danger, QMenu::item[text="Delete"] {{
    background-color: {DANGER_HOVER};
    padding: 8px 6px;
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

QMenu::icon:checked {{}}

/* Input */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
    border-color: {BORDER_LIGHT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {BORDER_LIGHT};
    background-color: {BG_INPUT};
}}
QLineEdit:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_DARK};
}}
QLineEdit[invalid="true"] {{
    border-color: {DANGER_HOVER};
}}

/* Combo box */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid;
    border-color: {BORDER};
    border-radius: 6px;
    padding: 6px;
}}
QComboBox:separator {{
    border: 1px solid {BORDER};
    margin: 0 8px;
}}
QComboBox:hover {{
    border-color: {BORDER_LIGHT};
}}
QComboBox:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_DARK};
}}
QComboBox[invalid="true"] {{
    border-color: {DANGER_HOVER};
}}
QComboBox:open {{
    border-color: {BORDER};
    background-color: {BG_INPUT};
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
    color: {TEXT_PRIMARY};
}}

QComboBox[compact="true"] {{
    padding: 4px 12px;
    min-height: 1em;
    max-height: 1em;
}}
QComboBox[compact="true"] ::item {{
    max-height: 1em;
    padding: 4px 4px;
}}

QComboBox[icons_only="true"] ::item {{
    height: 56px;
}}

QComboBox[bigIcons="true"] ::item {{
    min-height: 48px;
    icon-size: 32px;
    padding: 0 12px;
}}
QComboBox[bigIcons="true"] ::item:selected {{
    color: {TEXT_PRIMARY};
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

/* Progress bar
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
*/

/* Scrollbar
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
*/


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

/* Tooltips
QToolTip {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT};
    border-radius: 4px;
    padding: 4px 8px;
}}
*/

/* Status Bar */
QStatusBar {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
}}

QMenuSeparator, QToolSeparator, QSplitter, QSeparator {{
    border: 1px {BORDER};
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
"""

match sys.platform:
    # case "win32":
    #     mixin = f"""
    #         QMenu {{
    #             border-radius: 1px;
    #             icon-size: 16px;
    #             padding: 4px;
    #             background-color: {BG_SURFACE};
    #             background-clip: border;
    #             border: 1px solid {BORDER};
    #             font-size: 10pt;
    #         }}
    #         QMenu::item {{
    #             background-color: transparent;
    #             padding: 4px 6px;
    #             border-radius: 4px;
    #         }}
    #         QMenu::item[danger="true"] {{
    #             background-color: {DANGER};
    #         }}
    #         QMenu::icon {{
    #             top: 1px;
    #             left: 4px;
    #         }}
    #         QMenu::item:selected {{
    #             background-color: {BG_SURFACE_LIGHT};
    #         }}
    #         QMenu::item:disabled {{
    #             color: {TEXT_MUTED};
    #         }}

    #         QMenu::icon:checked {{}}
    #     """
    # template = "\n".join([template, mixin])
    case "darwin":
        pass
    case "linux":
        mixin = """
            QComboBox ::item {{
                min-height: 2em;
            }}
        """
        STYLESHEET = "\n".join([STYLESHEET, mixin])


# def regen_styles():
#     global STYLESHEET
#     STYLESHEET = template.format(**globals())
#     return STYLESHEET


# STYLESHEET = regen_styles()

FONT = QFont()
FONT.setFamilies(["Segoe UI", "sans-serif"])
FONT.setPointSize(10)
FONT_INF = QFontInfo(FONT)

TERMINAL_FONT = QFont()
TERMINAL_FONT.setFamilies(["consolas", "hack", "monospace"])
TERMINAL_FONT.setStyleHint(QFont.StyleHint.Monospace)
TERMINAL_FONT_INF = QFontInfo(TERMINAL_FONT)

CSANS = QFont("Comic Sans MS")
CSANS.setPointSize(9)
CSANS_INF = QFontInfo(CSANS)
CSANS_AVAILABLE = CSANS_INF.exactMatch()

uses_dark_mode = True
