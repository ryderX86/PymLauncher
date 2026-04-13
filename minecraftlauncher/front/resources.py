from functools import lru_cache
from typing import LiteralString, overload
from enum import StrEnum
import logging
import base64
import binascii
import zipfile

from PySide6.QtCore import Qt, QFile, QSize
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtSvg import QSvgRenderer

from . import _resources_bundled
from minecraftlauncher.args import resource_debug
from minecraftlauncher.front.styles import (
    uses_dark_mode, TEXT_PRIMARY, ACCENT_LIGHTER, ACCENT_LIGHT, ACCENT_HOVER,
    ACCENT, ACCENT_DIM, ACCENT_PRESS
)
from minecraftlauncher.back import version_manager
from minecraftlauncher.constants import LAUNCHER_DATA_DIR
from minecraftlauncher import config

_icon_cache:dict[str, QIcon] = {}
_svg_cache:dict[str, QSvgRenderer] = {}

log = logging.getLogger(__name__)
if not resource_debug:
    log.setLevel(logging.INFO)

BLOCK_TEXTURE_PATH = "assets/minecraft/textures/block/"
ENTITY_TEXTURE_PATH = "assets/minecraft/textures/entity/"
BLOCK_TEXTURE_CACHE = LAUNCHER_DATA_DIR / "icon_cache"

class BaseIconPath:
    def __init__(self, path:str, dm_path:str|None=None, *, ext:str|None=None):
        self._path = path
        self._dm_path = dm_path

        if ext:
            if not ext.startswith("."):
                ext = "." + ext
            self._ext = ext
        else:
            if self._dm_path and (self._path.split(".")[-1]
                                  != self._dm_path.split(".")[-1]):
                raise TypeError("Both paths must be the same filetype!")
            self._ext = ""

    @property
    def path(self):
        if uses_dark_mode and self._dm_path:
            return self._dm_path + self._ext
        return self._path + self._ext
    
class SymbolPath(BaseIconPath):
    _BASE = ":/icon/symbol/"
    def __init__(self, filename:str, dark_filename:str|None=None, *,
                 make_dm:bool=True):
        filename = self._BASE + filename
        if dark_filename:
            dark_filename = self._BASE + dark_filename
        elif make_dm:
            dark_filename = (
                filename.split(".")[0] + "-light" + ".svg"
            )
        super().__init__(filename, dark_filename)

def icon_highlight_fix(icon:QIcon, pixmap:QPixmap|None=None,
                       filename:str|None=None):
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

def symbol(name:str):
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
        raise ValueError("Symbol '%s' not in resources" % name)
    if QFile.exists(dark_name) and not uses_dark_mode:
        name = dark_name
        disabled_name = disabled_dark_name
    log.debug("Creating QIcon for '%s'" % name)
    icon = icon_highlight_fix(QIcon(name), filename=name)
    if QFile.exists(disabled_name):
        icon.addFile(disabled_name, QSize(), QIcon.Mode.Disabled)
    _icon_cache[name] = icon
    return icon

def animation(name:str):
    """
    Returns bytes with the specified animated SVG

    Changes the SVG depending on color scheme.

    Raises a ValueError if the svg isn't found.
    """
    PATH = ":/animation/%s.svg" % name
    if not QFile.exists(PATH):
        raise ValueError("Couldn't find animation name!")
    log.debug("Creating QSvgRenderer for '%s'" % PATH)
    file = QFile(PATH)
    file.open(QFile.OpenModeFlag.ReadOnly)
    file_data = file.readAll().data()
    if isinstance(file_data, (bytes, bytearray)):
        file_contents = file_data.decode("utf-8")
    elif isinstance(file_data, memoryview):
        file_contents = file_data.tobytes().decode("utf-8")
    else:
        raise TypeError(
            "Unexpected type in 'QFile(%s).readAll().data()'" % PATH
        )
    file_contents = file_contents.replace("{primary_dark}", ACCENT_PRESS)
    file_contents = file_contents.replace("{primary}", ACCENT)
    file_contents = file_contents.replace("{primary_light}", ACCENT_HOVER)
    file_contents = file_contents.replace("{primary_lightest}", ACCENT_LIGHT)
    file_contents = file_contents.replace("{primary_surface}", ACCENT_LIGHTER)
    file_contents = file_contents.replace("{surface}", TEXT_PRIMARY)
    svg_bytes = file_contents.encode("utf-8")
    return svg_bytes

PROF_ICON_LIST = [
    "Bedrock", "Bookshelf", "Brick", "Cake", "Pumpkin", "Chest", "Clay",
    "Coal_Block", "Coal_Ore", "Cobblestone", "Crafting_Table",
    "Creeper_Head", "Diamong_Block", "Diamond_Ore", "Dirt", "Podzol",
    "Dirt_Snow", "Emerald_Block", "Emerald_Ore", "Enchanting_Table",
    "End_Stone", "Farmland", "Furnace", "Furnace_On", "Glass",
    "Glazed_Terracotta_Light_Blue", "Glazed_Terracotta_Orange",
    "Glazed_Terracotta_White", "Glowstone", "Gold_Block", "Gold_Ore",
    "Grass", "Gravel", "Hardened_Clay", "Ice_Packed", "Iron_Block",
    "Iron_Ore", "Lapis_Ore", "Leaves_Oak", "Leaves_Jungle", "Leaves_Birch",
    "Leaves_Spruce", "Lectern", "Log_Acacia", "Log_Birch", "Log_DarkOak",
    "Log_Jungle", "Log_Oak", "Log_Spruce", "Mycelium", "Nether_Brick",
    "Netherrack", "Obsidian", "Planks_Acacia", "Planks_DarkOak",
    "Planks_Jungle", "Planks_Oak", "Planks_Spruce", "Quartz_Ore",
    "Red_Sand", "Red_Sandstone", "Redstone", "Redstone_Block", "Sand",
    "Sandstone", "Skeleton_Skull", "Snow", "Soul_Sand", "Stone",
    "Stone_Andesite", "Stone_Diorite", "Stone_Granite", "TNT", "Water", "Wool"
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
        

def profile_icon(name_or_b64:str):
    BASE = ":/profile/"
    is_b64 = (name_or_b64.startswith("data:image/")
              and "base64" in name_or_b64[:25])
    
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
        name_or_b64 = name_or_b64.lower() # official launcher uses uppercase
        if name_or_b64 in _icon_cache:
            return _icon_cache[name_or_b64]
        path = BASE + name_or_b64 + ".png"
        if not QFile.exists(path):
            return get_unknown_icon()
        log.debug("Creating QIcon for profile icon '%s'" % name_or_b64)
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

def icon_from_qimg(img:QImage, scale_pixels:bool=False):
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
            w, h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )
    else:
        img_ = img
    pix = QPixmap.fromImage(img_)
    ico = icon_highlight_fix(QIcon(pix), pixmap=pix)
    if img_id:
        _icon_cache[img_id] = ico
        return _icon_cache[img_id]
    return ico