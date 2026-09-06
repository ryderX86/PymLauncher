from datetime import datetime, timedelta
import base64
import binascii
import logging
import os

from PySide6.QtCore import QFile, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
import qrcode
import qrcode.constants
import qrcode.image.svg

from launcher.constants import OS
from launcher.front.styles import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_LIGHT,
    ACCENT_LIGHTER,
    ACCENT_PRESS,
    TEXT_PRIMARY,
    uses_dark_mode,
)
from launcher.launchargs import launchargs
from launcher.paths import paths

from . import _resources_bundled  # pylint: disable=W0611

_icon_cache: dict[str, QIcon] = {}

log = logging.getLogger(__name__)
if not launchargs.resource_debug:
    log.setLevel(logging.INFO)


class BaseIconPath:
    __slots__ = ("_path", "_dm_path", "_ext")

    def __init__(
        self, path: str, dm_path: str | None = None, *, ext: str | None = None
    ):
        self._path = path
        self._dm_path = dm_path

        if ext:
            if not ext.startswith("."):
                ext = "." + ext
            self._ext = ext
        else:
            if self._dm_path and (
                self._path.split(".")[-1] != self._dm_path.split(".")[-1]
            ):
                raise TypeError("Both paths must be the same filetype!")
            self._ext = ""

    @property
    def path(self):
        if uses_dark_mode and self._dm_path:
            return self._dm_path + self._ext
        return self._path + self._ext


class SymbolPath(BaseIconPath):
    _BASE = ":/icon/symbol/"

    def __init__(
        self,
        filename: str,
        dark_filename: str | None = None,
        *,
        make_dm: bool = True,
    ):
        filename = self._BASE + filename
        if dark_filename:
            dark_filename = self._BASE + dark_filename
        elif make_dm:
            dark_filename = filename.split(".")[0] + "-light" + ".svg"
        super().__init__(filename, dark_filename)


def icon_highlight_fix(
    icon: QIcon, pixmap: QPixmap | None = None, filename: str | None = None
):
    """Quick fix for Qt highlighting selected items with icons."""
    if pixmap:
        icon.addPixmap(pixmap, QIcon.Mode.Selected)
        icon.addPixmap(pixmap, QIcon.Mode.Active)
    elif filename:
        icon.addFile(filename, QSize(), QIcon.Mode.Selected)
        icon.addFile(filename, QSize(), QIcon.Mode.Active)
    else:
        raise TypeError(
            "Must have argument 'pixmap' or 'filename' (both are NoneType)"
        )
    return icon


def symbol(name: str):
    """
    Returns a `QIcon()` object

    The name argument is turned into `f":/icon/symbol/{name}.svg"` (and
    "...-light.svg" for dark-mode icons when applicable/existing)

    Raises ValueError if the symbol doesn't exist
    """
    if name in _icon_cache:
        return _icon_cache[name]
    dark_name = f":/icon/symbol/{name}-dark.svg"
    name = f":/icon/symbol/{name}.svg"
    disabled_name = f":/icon/symbol/{name}-disabled.svg"
    disabled_dark_name = f":/icon/symbol/{name}-disabled-dark.svg"
    if not QFile.exists(name):
        raise FileNotFoundError(f"Symbol '{name}' not in resources")
    if QFile.exists(dark_name) and not uses_dark_mode:
        name = dark_name
        disabled_name = disabled_dark_name
    log.debug("Creating QIcon for '%s'", name)
    icon = icon_highlight_fix(QIcon(name), filename=name)
    if QFile.exists(disabled_name):
        icon.addFile(disabled_name, QSize(), QIcon.Mode.Disabled)
    _icon_cache[name] = icon
    return icon


def animation(name: str):
    """
    Returns bytes with the specified animated SVG

    Changes the SVG depending on color scheme.

    Raises a ValueError if the svg isn't found.
    """
    path = f":/animation/{name}.svg"
    if not QFile.exists(path):
        raise ValueError("Couldn't find animation name!")
    log.debug("Creating QSvgRenderer for '%s'", path)
    file = QFile(path)
    file.open(QFile.OpenModeFlag.ReadOnly)
    file_data = file.readAll().data()
    if isinstance(file_data, (bytes, bytearray)):
        file_contents = file_data.decode("utf-8")
    elif isinstance(file_data, memoryview):
        file_contents = file_data.tobytes().decode("utf-8")
    else:
        raise TypeError("Unexpected type in 'QFile().readAll().data()'")
    file_contents = file_contents.replace("{primary_dark}", ACCENT_PRESS)
    file_contents = file_contents.replace("{primary}", ACCENT)
    file_contents = file_contents.replace("{primary_light}", ACCENT_HOVER)
    file_contents = file_contents.replace("{primary_lightest}", ACCENT_LIGHT)
    file_contents = file_contents.replace("{primary_surface}", ACCENT_LIGHTER)
    file_contents = file_contents.replace("{surface}", TEXT_PRIMARY)
    svg_bytes = file_contents.encode("utf-8")
    return svg_bytes


PROF_ICON_LIST = [
    "Bedrock",
    "Bookshelf",
    "Brick",
    "Cake",
    "Pumpkin",
    "Chest",
    "Clay",
    "Coal_Block",
    "Coal_Ore",
    "Cobblestone",
    "Crafting_Table",
    "Creeper_Head",
    "Diamond_Block",
    "Diamond_Ore",
    "Dirt",
    "Podzol",
    "Dirt_Snow",
    "Emerald_Block",
    "Emerald_Ore",
    "Enchanting_Table",
    "End_Stone",
    "Farmland",
    "Furnace",
    "Furnace_On",
    "Glass",
    "Glazed_Terracotta_Light_Blue",
    "Glazed_Terracotta_Orange",
    "Glazed_Terracotta_White",
    "Glowstone",
    "Gold_Block",
    "Gold_Ore",
    "Grass",
    "Gravel",
    "Hardened_Clay",
    "Ice_Packed",
    "Iron_Block",
    "Iron_Ore",
    "Lapis_Ore",
    "Leaves_Oak",
    "Leaves_Jungle",
    "Leaves_Birch",
    "Leaves_Spruce",
    "Lectern",
    "Log_Acacia",
    "Log_Birch",
    "Log_DarkOak",
    "Log_Jungle",
    "Log_Oak",
    "Log_Spruce",
    "Mycelium",
    "Nether_Brick",
    "Netherrack",
    "Obsidian",
    "Planks_Acacia",
    "Planks_DarkOak",
    "Planks_Jungle",
    "Planks_Oak",
    "Planks_Spruce",
    "Quartz_Ore",
    "Red_Sand",
    "Red_Sandstone",
    "Redstone",
    "Redstone_Block",
    "Sand",
    "Sandstone",
    "Skeleton_Skull",
    "Snow",
    "Soul_Sand",
    "Stone",
    "Stone_Andesite",
    "Stone_Diorite",
    "Stone_Granite",
    "TNT",
    "Water",
    "Wool",
]


def get_unknown_icon():
    # return symbol("missing")
    NAME = ":/profile/default.png"
    if NAME in _icon_cache:
        return _icon_cache[NAME]
    else:
        log.debug("Creating profile unknown/default QIcon")
        pix = QPixmap(NAME)
        _icon_cache[NAME] = QIcon(pix)
        return _icon_cache[NAME]


def profile_icon(name_or_b64: str):
    BASE = ":/profile/"
    is_b64 = (
        name_or_b64.startswith("data:image/") and "base64" in name_or_b64[:25]
    )

    if is_b64:
        b64_hash = abs(hash(name_or_b64)).to_bytes(8, "big").hex()
        if b64_hash in _icon_cache:
            return _icon_cache[b64_hash]

        log.debug("Creating QIcon for base64 profile icon...")

        # in case for some reason a JPEG is allowed in:
        imgtype = name_or_b64[11:15]
        if imgtype.endswith(";"):
            imgtype = imgtype[:3]
        b64_start = 19 + len(imgtype)
        b64 = name_or_b64[b64_start:]

        # the base64 module throws a tantrum when there's "not enough" padding
        while len(b64) % 3 != 0:
            b64 = b64 + "="

        try:
            img_bytes = base64.b64decode(b64)
        except binascii.Error:
            log.warning("Failed to get base64 data for profile icon")
            return get_unknown_icon()
        pix = QPixmap()
        loaded = pix.loadFromData(img_bytes)
        if not loaded:
            log.warning("QPixmap failed to get base64 image, defaulting...")
            return get_unknown_icon()
        _icon_cache[b64_hash] = icon_highlight_fix(QIcon(pix), pixmap=pix)
        return _icon_cache[b64_hash]
    else:
        name_or_b64 = name_or_b64.lower()  # official launcher uses uppercase
        if name_or_b64 in _icon_cache:
            return _icon_cache[name_or_b64]
        path = BASE + name_or_b64 + ".png"
        if not QFile.exists(path):
            return get_unknown_icon()
        log.debug("Creating QIcon for profile icon '%s'", name_or_b64)
        _icon_cache[name_or_b64] = icon_highlight_fix(
            QIcon(path), filename=path
        )
        return _icon_cache[name_or_b64]


def get_all_default_icons() -> dict[str, QIcon]:
    icons = {}
    built_icons = []
    # skip the default icon
    built_icons.append(get_unknown_icon())
    for name in PROF_ICON_LIST:
        ico = profile_icon(name)
        if ico in built_icons:
            del ico
            continue
        icons[name] = ico
        built_icons.append(ico)
    del built_icons
    return icons


def icon_from_qimg(img: QImage, scale_pixels: bool = False):
    img_id = img.text("id")
    if img_id:
        img_id = "IMG_" + img_id
        if img_id in _icon_cache:
            return _icon_cache[img_id]
    else:
        log.warning(
            "Image has no ID set! Memory leak may occur if this is re-used."
        )
    if scale_pixels:
        w = img.width() * 8
        h = img.height() * 8
        img_ = img.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    else:
        img_ = img
    pix = QPixmap.fromImage(img_)
    ico = icon_highlight_fix(QIcon(pix), pixmap=pix)
    if img_id:
        _icon_cache[img_id] = ico
        return _icon_cache[img_id]
    return ico


def link_to_qrcode(link: str):
    factory = qrcode.image.svg.SvgPathFillImage

    qr = qrcode.QRCode(
        box_size=10,
        image_factory=factory,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(link)
    qr.make()
    svg_el = qr.make_image()
    wh = svg_el.pixel_size
    svg = svg_el.to_string().decode()
    svg = svg.replace("mm", "px")
    pix = QPixmap()
    pix.loadFromData(svg.encode())
    pix = pix.scaledToWidth(wh // 2)
    return pix


# used in cache_icon() for OS-specific icons
# windows tends to ONLY use ICO files while POSIX systems like anything really
match OS:
    case "windows":
        _ICO_FMT = "ICO"
        _ICO_SUFFIX = "ico"
    case _:
        _ICO_FMT = "PNG"
        _ICO_SUFFIX = "png"


def cache_icon(ico: QIcon | QPixmap, name: str):
    """
    Semi-expensive operation to store a QIcon as an .ico (windows) or
    .png (literally any other OS) for jump-list use, primarily.

    If the file exists but is under a week old, the icon won't be re-cached
    unless the user clears the icon cache manually. Afterwards it'll overwrite
    the ico.

    Returns the full file path as a string.
    """
    dir_ = os.path.join(paths.textures_cache, "icons")
    if not os.path.isdir(dir_):
        log.debug("Creating icons cache folder: '%s'", dir_)
        os.mkdir(dir_)
    fp = os.path.join(dir_, f"{name}.{_ICO_SUFFIX}")
    if os.path.isfile(fp):
        ts = os.stat(fp).st_mtime
        if ts > (datetime.now() - timedelta(days=7)).timestamp():
            return str(fp)
    if isinstance(ico, QIcon):
        # get the max available icon size which absolutely REQUIRES a QSize
        # instance for SOME reason, but we can just spam it with 9999 since Qt
        # will take the QSize down to the maximum, pretty much the same as
        # if you did ```min(max_size, wanted_size)``` in python
        size = ico.actualSize(QSize(9999, 9999))
        ico = ico.pixmap(size)

    # ico should be a QPixmap now

    log.debug("Saving icon to '%s'", fp)
    ico.save(str(fp), _ICO_FMT)
    return str(fp)
