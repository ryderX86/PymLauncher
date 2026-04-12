from typing import Any
from functools import lru_cache
import logging
import json
import xml

from minecraftlauncher.constants import LAUNCHER_DATA_DIR, MINECRAFT_DIR
from minecraftlauncher.back.download_manager import (
    download, should_download_file, file_exists_or_age
)

VERSION_LIST_URL = ("https://maven.minecraftforge.net/net/minecraftforge/forge"
                    "/maven-metadata.xml")
VERSION_LIST_RECOMMENDED = ("https://files.minecraftforge.net/net/minecraftfor"
                            "ge/forge/promotions_slim.json")