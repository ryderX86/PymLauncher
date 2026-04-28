from pathlib import Path
from xml.etree import ElementTree
import logging
import subprocess
import platform


TEXT_PRIMARY = "#e0e0e0"

log = logging.getLogger("ico")

WORKDIR = Path(__file__).parent

PROJ_LICENSE = WORKDIR / "project_license.txt"
OTHER_LICENSE = WORKDIR / "acknowledgements.txt"
INSTALLER_LICENSE = WORKDIR / "dist" / "license.txt"

project_license = PROJ_LICENSE.read_text()
other_license = OTHER_LICENSE.read_text()

INSTALLER_LICENSE.write_text("\n".join([project_license, other_license]))

print("Successfully combined the license files.")

ElementTree.register_namespace("", "http://www.w3.org/2000/svg")


def change_color(raw_xml: str):
    xml = ElementTree.fromstring(raw_xml)
    if xml.tag != "svg" and xml.tag != "{http://www.w3.org/2000/svg}svg":
        log.warning("change_color(): XML element is not <svg>, returning.")
        print(xml.tag)
        return raw_xml
    xml.attrib["fill"] = TEXT_PRIMARY
    return ElementTree.tostring(xml, encoding="unicode")


def change_color_dark(raw_xml: str):
    xml = ElementTree.fromstring(raw_xml)
    if xml.tag != "svg" and xml.tag != "{http://www.w3.org/2000/svg}svg":
        log.warning("change_color(): XML element is not <svg>, returning.")
        print(xml.tag)
        return raw_xml
    xml.attrib["fill"] = "current_color"
    return ElementTree.tostring(xml, encoding="unicode")


ICON_DIR = WORKDIR / "icon"

DEBUG = False

for file in ICON_DIR.rglob("*.svg"):
    if "animate" in str(file):
        continue
    if file.stem.endswith("-light"):
        print("Deleting '%s' (-light...)" % file.name)
        file.unlink()
        continue
    if file.stem.endswith("-dark"):
        continue
    if not file.is_file():
        continue
    old_text = file.read_text()
    new_text = change_color(file.read_text())
    if DEBUG:
        print("Found '%s'" % file)
        print("  " + old_text.replace("\n", "\n  "))
        print("  " + new_text.replace("\n", "\n  "))
        continue
    dark_file = file.parent / (file.stem + "-dark" + file.suffix)
    if not dark_file.exists():
        dark_file.write_text(change_color_dark(old_text))
    if file.read_text() == new_text:
        continue
    file.write_text(new_text)

qrc_name = ICON_DIR.parent / "resources.qrc"
output_res_file = (
    ICON_DIR.parent.parent
    / "minecraftlauncher"
    / "front"
    / "_resources_bundled.py"
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
