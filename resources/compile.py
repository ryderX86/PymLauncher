from pathlib import Path
from xml.etree import ElementTree
import logging
import platform
import subprocess

TEXT_PRIMARY = "#FFFFFF"

log = logging.getLogger("ico")

WORKDIR = Path(__file__).parent

PROJ_LICENSE = WORKDIR / "project_license.txt"
OTHER_LICENSE = WORKDIR / "acknowledgements.txt"
INSTALLER_LICENSE = WORKDIR / "dist" / "distributed-license.txt"

project_license = PROJ_LICENSE.read_text()

INSTALLER_LICENSE.write_text(project_license)

print("Successfully combined the license files.")

ElementTree.register_namespace("", "http://www.w3.org/2000/svg")


def change_color(raw_xml: str):
    xml = ElementTree.fromstring(raw_xml)
    if xml.tag != "svg" and xml.tag != "{http://www.w3.org/2000/svg}svg":
        log.warning("change_color(): XML element is not <svg>, returning.")
        print(xml.tag)
        return raw_xml
    p = xml.find("{http://www.w3.org/2000/svg}path")
    if p is not None:
        p.attrib["fill"] = TEXT_PRIMARY

    return ElementTree.tostring(xml, encoding="unicode")


def change_color_dark(raw_xml: str):
    xml = ElementTree.fromstring(raw_xml)
    if xml.tag != "svg" and xml.tag != "{http://www.w3.org/2000/svg}svg":
        log.warning("change_color(): XML element is not <svg>, returning.")
        print(xml.tag)
        return raw_xml
    p = xml.find("{http://www.w3.org/2000/svg}path")
    if p is not None:
        p.attrib["fill"] = "current_color"
    return ElementTree.tostring(xml, encoding="unicode")


ICON_DIR_LIGHT = WORKDIR / "icons" / "fallback" / "light"
ICON_DIR_DARK = WORKDIR / "icons" / "fallback" / "dark"

DEBUG = False

for file in ICON_DIR_DARK.rglob("*.svg"):
    if "animate" in str(file):
        continue
    if not file.is_file():
        continue
    old_text = file.read_text()
    new_text = change_color_dark(file.read_text())
    light_file = ICON_DIR_LIGHT / file.name
    if not light_file.exists():
        light_file.write_text(change_color(old_text))
    if file.read_text() == new_text:
        continue
    file.write_text(new_text)

qrc_name = WORKDIR / "resources.qrc"
output_res_file = (
    WORKDIR.parent / "launcher" / "front" / "_resources_bundled.py"
)
cmd = [
    "cmd.exe",
    "/c",
    "pyside6-rcc",
    str(qrc_name),
    "-o",
    str(output_res_file),
]
if platform.system() != "Windows":
    cmd = cmd[2:]
    cmd[0] = str(WORKDIR.parent / ".venv" / "bin" / "pyside6-rcc")
res = subprocess.run(
    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
)
print(res.stdout.decode())
print(res.stderr.decode())

if res.returncode != 0:
    print("Failed to compile QRC")
    exit(1)

# output_text = output_res_file.read_text()
# output_res_file.write_text(
#     output_text.replace("PySide6", "PyQt6")
# )
print("Successfully compiled QRC resources.")
