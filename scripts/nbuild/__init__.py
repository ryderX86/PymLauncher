from argparse import ArgumentParser
from enum import IntFlag
from pathlib import Path
import logging
import os
import platform
import tomllib


class BuildFlags(IntFlag):
    NONE = 0b00000
    NO_BUILD_BUMP = 0b01000
    EXECUTABLE = 0b00001
    INSTALLER = 0b00010
    RESOURCES = 0b00100
    WEBVIEW = 0b10000
    ALL = 0b11111


CWD = Path(__file__).parent.parent.parent
VENV_PATH = CWD / ".venv"

_parser = ArgumentParser("Build-script")
_parser.add_argument("-d", "--debug", action="store_true", default=False)
_parser.add_argument(
    "-r", "--build-report", action="store_true", default=False
)
_parser.add_argument(
    "-e", "--exe", "--executable", action="store_true", default=False
)
_parser.add_argument("-i", "--installer", action="store_true", default=False)
_parser.add_argument("-s", "--resources", action="store_true", default=False)
_parser.add_argument("-n", "--no-bump", action="store_true", default=False)
_parser.add_argument("-aci", "--azure-client-id", type=str, default=None)
_parser.add_argument("--noinclude-webview", action="store_true", default=False)

_args = _parser.parse_args()

DEBUG: bool = _args.debug
MAKE_BUILD_REPORT: bool = _args.build_report
EXECUTABLE_BUILD: bool = _args.exe
INSTALLER_BUILD: bool = _args.installer
RESOURCES_BUILD: bool = _args.resources
BUMP: bool = not _args.no_bump
AZURE_CLIENT_ID: str | None = _args.azure_client_id
CLIENT_ID_FP = Path(__file__).parent.parent.parent / ".azure-client-id"
INCLUDE_WEBVIEW: bool = not _args.noinclude_webview

FLAGS = BuildFlags.ALL
if EXECUTABLE_BUILD or INSTALLER_BUILD or RESOURCES_BUILD:
    FLAGS = BuildFlags.NONE
    if EXECUTABLE_BUILD:
        FLAGS |= BuildFlags.EXECUTABLE
    if INSTALLER_BUILD:
        FLAGS |= BuildFlags.INSTALLER
    if RESOURCES_BUILD:
        FLAGS |= BuildFlags.RESOURCES
    if INCLUDE_WEBVIEW:
        FLAGS |= BuildFlags.WEBVIEW
if not BUMP:
    FLAGS |= BuildFlags.NO_BUILD_BUMP
for flag in BuildFlags:
    if FLAGS & flag:
        print(f"Flag {flag.name} present")

if AZURE_CLIENT_ID:
    os.environ["AZURE_CLIENT_ID"] = AZURE_CLIENT_ID
elif CLIENT_ID_FP.exists() and CLIENT_ID_FP.is_file():
    client_id = CLIENT_ID_FP.read_text()
    os.environ["AZURE_CLIENT_ID"] = client_id

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

RESOURCE_COMPILE_SCRIPT = CWD / "resources" / "compile.py"
ICO_PATH = CWD / "resources" / "dist" / "icon.ico"

_toml_p = CWD / "pyproject.toml"
PROJECT_TOML = tomllib.loads(_toml_p.read_text())
version: str = PROJECT_TOML["project"]["version"]


def bump_build_number():
    txt = _toml_p.read_text()
    version_nums = version.split(".")
    bnum = version_nums[-1]
    if not bnum.isdigit():
        logging.warning("Bad version number: %r; not bumping", bnum)
        return
    version_nums[-1] = str(int(bnum) + 1)
    version_new = ".".join(version_nums)
    txt = txt.replace(
        f'\nversion = "{version}"\n', f'\nversion = "{version_new}"\n'
    )
    logging.info("Bumping build number from %r => %r", version, version_new)
    _toml_p.write_text(txt)


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
if (not FLAGS & BuildFlags.WEBVIEW) or platform.system() not in [
    "Windows",
    "Darwin",
]:
    NOINCLUDE_DATA.add("PySide6/qml/QtWebView/*")

NOINCLUDE_LIBS = {
    "Qt6DataVisualization*",
    "Qt6LabsWaveFrontMesh",
    "Qt6Multimedia*",
    "Qt6Pdf*",
    "Qt6Quick3DParticle*",
    "Qt6Quick3DXr*",
    "*TextToSpeech*",
    "Qt6VirtualKeyboard*",
    "Qt6WebEngine",
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
    "*QtWebEngine*",
    "*qtwebengine*",
}
if (not FLAGS & BuildFlags.WEBVIEW) or platform.system() not in [
    "Windows",
    "Darwin",
]:
    NOINCLUDE_LIBS.add("Qt6Web*")

INCLUDE_PLUGINS = {
    "sensible",
    "qml",
}

if (not FLAGS & BuildFlags.WEBVIEW) and platform.system() in [
    "Windows",
    "Darwin",
]:
    INCLUDE_PLUGINS.add("webview")

BASE_ARGS = [
    "--standalone",
    "--show-anti-bloat-changes",
    # source changes are console debug args anyways, no reason not to show them
    "--show-source-changes=*",
    "--python-flag=-m",
    # don't include libs from the user's python install
    "--python-flag=isolated",
    # remove assert statements and docstrings
    "--python-flag=-OO",
    "--enable-plugin=pyside6",
    f"--include-qt-plugins={",".join(INCLUDE_PLUGINS)}",
    "--output-dir=./dist",
    # pyside6-deploy includes these and they seem to just be anti-bloat, so no
    # harm in including them here too:
    "--noinclude-dlls=*.cpp.o",
    "--noinclude-dlls=*.qsb",
]

if MAKE_BUILD_REPORT:
    BASE_ARGS.append("--report=./dist/build-report.xml")
if DEBUG:
    BASE_ARGS.append("--verbose-output=./dist/verbose-output.txt")
