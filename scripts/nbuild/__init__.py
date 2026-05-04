from argparse import ArgumentParser
from pathlib import Path
import logging
import tomllib

CWD = Path(__file__).parent.parent.parent
VENV_PATH = CWD / ".venv"

_parser = ArgumentParser("Build-script")
_parser.add_argument("-d", "--debug", action="store_true", default=False)

_args = _parser.parse_args()

DEBUG: bool = _args.debug

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

RESOURCE_COMPILE_SCRIPT = CWD / "resources" / "compile.py"
ICO_PATH = CWD / "resources" / "dist" / "icon.ico"

_toml_p = CWD / "pyproject.toml"
PROJECT_TOML = tomllib.loads(_toml_p.read_text())

NOINCLUDE_DATA = {
    "PySide6/qml/QtWebEngine/*",
    "PySide6/qml/Qt5Compat/*",
    "PySide6/qml/QtCharts/*",
    "PySide6/qml/QtDataVisualization/*",
    "PySide6/qml/QtGraphs/*",
    "PySide6/qml/QtLocation/*",
    "PySide6/qml/QtMultimedia/*",
    "PySide6/qml/QtRemoteObjects/*",
    "PySide6/qml/QtScxml/*",
    "PySide6/qml/QtSensors/*",
    "PySide6/qml/QtTest/*",
    "PySide6/qml/QtTextToSpeech/*",
    "PySide6/qml/QtWebChannel/*",
    "PySide6/qml/QtWebSockets/*",
    "PySide6/qml/QtWebView/*",
    "PySide6/qml/Qt/*",
    "PySide6/qml/QtCore/*",
    "PySide6/qml/QtNetwork/*",
    "PySide6/qml/QtPositioning/*",
    "PySide6/qml/QtQuick/Controls/*",
    "PySide6/qml/QtQuick/Dialogs/*",
    "PySide6/qml/QtQuick/Effects/*",
    "PySide6/qml/QtQuick/Layouts/*",
    "PySide6/qml/QtQuick/LocalStorage/*",
    "PySide6/qml/QtQuick/NativeStyle/*",
    "PySide6/qml/QtQuick/Pdf/*",
    "PySide6/qml/QtQuick/Scene2D/*",
    "PySide6/qml/QtQuick/Scene3D/*",
    "PySide6/qml/QtQuick/Shapes/*",
    "PySide6/qml/QtQuick/Templates/*",
    "PySide6/qml/QtQuick/tooling/*",
    "PySide6/qml/QtQuick/VectorImage/*",
    "PySide6/qml/QtQuick/VirtualKeyboard/*",
    "PySide6/qml/QtQuick/Window/*",
    "PySide6/qml/QtQuick/lightmapviewer/*",
    "PySide6/qml/QtQuick/MaterialEditor/*",
    "PySide6/qml/QtQuick/ParticleEffects/*",
    "PySide6/qml/QtQuick/Particles3D/*",
    "PySide6/qml/QtQuick/SpacialAudio/*",
    "PySide6/qml/QtQuick/Xr/*",
}

NOINCLUDE_LIBS = {
    "Qt6DataVisualization*",
    "Qt6LabsWaveFrontMesh",
    "Qt6Multimedia*",
    "Qt6Pdf*",
    "Qt6Quick3DParticle*",
    "Qt6Quick3DXr*",
    "*TextToSpeech*",
    "Qt6VirtualKeyboard*",
    "Qt6Web*",
    "Qt6QuickControls2*",
    "Qt6Quick3DEffects",
    "Qt6Sensor*",
    "*SpacialAudio*",
    "Qt6Sql.dll",
    "*statemachine*",
    "*test*",
    "Qt63DAnimation",
    "Qt63DCore",
    "Qt63DExtras",
    "Qt63DInput",
    "Qt63DLogic",
    "Qt63DRender",
    "Qt6Labs*",
    "Qt6QuickDialogs*",
    "Qt6Charts*",
    "Qt6Graphs*",
    "Qt6PositioningQuick",
    "Qt6Quick3DHelpersImpl",
    "Qt6Quick3DSpatialAudio",
    "Qt*Particle*",
}
