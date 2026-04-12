"""
minecraftlauncher.constants

Probably a better way to do this, but this is
where constant variables that need to be
globally referenced will remain (like the
Azure Client ID)
"""

from pathlib import Path
from typing import Literal
import os
import sys
import platform

from .args import work_dir
from . import DEV

offline_mode = False
"""
Monkey-patch-able variable for all modules to know if we
should be operating offline or not.
"""

LAUNCHER_NAME = "minecraftlauncher-python"
LAUNCHER_VERSION = "build-0"
AUTHOR_USR = "ryderX86"
EMAIL = "ryder@r86.me"

# Authentication URLs
AZURE_CLIENT_ID = "00000000402B5328" # Official MC launcher client ID
AZURE_SCOPE = "openid offline_access XboxLive.signin"
MS_DEVICE_CODE_URL = "https://login.live.com/oauth20_connect.srf"
MS_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
MSA_REFRESH_URL = "https://login.live.com/oauth20_token.srf"

XBOX_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"

MOJ_AUTH_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"

# Mojang API URLs
LAUNCH_ENTITLEMENTS_URL = "https://api.minecraftservices.com/entitlements/mcstore"
MOJ_PROF_URL = "https://api.minecraftservices.com/minecraft/profile"
SKIN_CHANGE_URL = "https://api.minecraftservices.com/minecraft/profile/skins"
CAPE_URL = "https://api.minecraftservices.com/minecraft/profile/capes/active"

# Game assets URLs
VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES_URL = "https://resources.download.minecraft.net"
LIBRARIES_URL = "https://libraries.minecraft.net"
JAVA_MANIFEST_URL = "https://launchermeta.mojang.com/v1/products/java-runtime/2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"

# Default paths
_plat = platform.system()
base:Path
if work_dir:
    base = work_dir
else:
    match _plat:
        case "Windows":
            base = Path("~\\AppData\\Roaming").expanduser().resolve()
        case "Linux":
            base = Path("~").expanduser().resolve()
        case "Darwin":
            base = Path("~/Library/Application Support").expanduser().resolve()
        case _:
            base_ = os.environ.get("XDG_DATA_HOME",
                                Path("~/.local/share").expanduser().resolve())
            base = Path(base_)
            del base_

MINECRAFT_DIR = base / ".minecraft"
LAUNCHER_DATA_DIR = base / LAUNCHER_NAME
LAUNCHER_CONFIG_FILE = LAUNCHER_DATA_DIR / "config.json"

if DEV:
    dev_base = Path(__file__).parent.parent / '.minecraft'
    if dev_base.exists() and dev_base.is_dir():
        base = dev_base
        MINECRAFT_DIR = base
        LAUNCHER_DATA_DIR = base / LAUNCHER_NAME
        LAUNCHER_CONFIG_FILE = LAUNCHER_DATA_DIR / "config.json"

OS:Literal["windows", "osx", "linux", "unknown"]
OS_PATH_DELIM:Literal["\\", "/"] = "/"
match platform.system():
    case "Windows":
        OS = "windows"
        OS_PATH_DELIM = "\\"
    case "Darwin":
        OS = "osx"
    case "Linux":
        OS = "linux"
    case _:
        OS = "unknown"

ARCH:Literal["x86_64", "x86", "arm64", "unknown"]
match platform.machine().lower():
    case "amd64" | "x86_64":
        ARCH = "x86_64"
    case "aarch64" | "arm64":
        ARCH = "arm64"
    case "i386" | "i686" | "x86" | "x86_32":
        ARCH = "x86"
    case _:
        ARCH = "unknown"

OS_VER:str = platform.version()

CLASSPATH_SEPARATOR = ";" if OS == "windows" else ":"

# TODO: cross-os compat
MOJANG_JAVA_PATH = Path("C:\\Program Files%s\\Minecraft Launcher\\runtime"
                        % (" (x86)" if ARCH == "x86" else ""))

JAVA_PATH = MINECRAFT_DIR / "jre"

show_snapshots:bool = True
"""
Whether or not snapshots/pre-releases should be shown in the versions list.
"""
show_old_releases:bool = True
"""
Whether or not old releases (pre-alpha, alpha, beta, etc.) should be shown in
the versions list.
"""

# profile stuff
DEFAULT_JVM_ARGS = " ".join([
    "-XX:+UnlockExperimentalVMOptions", "-XX:+UseG1GC",
    "-XX:G1NewSizePercent=20", "-XX:G1ReservePercent=20",
    "-XX:MaxGCPauseMillis=50", "-XX:G1HeapRegionSize=32M"
])

LOG4J_FIX_TIME = "2023-06-07T10:50:16+00:00"
LOG4J_116_5_FIX_MAX_TIME = "2021-06-08T11:00:39+00:00"
LOG4J_17_112_FIX_MAX_TIME = "2017-06-02T13:50:27+00:00"
LOG4J_VULN_MIN_TIME = "2013-09-26T15:11:19+00:00"

# resource bundling
_BASE_RES = getattr(sys, "_MEIPASS",
                    str(Path(__file__).parent.parent))
RES_PATH = Path(_BASE_RES) / "resources"

# uuids
PROFILE_MHF_STEVE = "c06f89064c8a49119c29ea1dbd1aab82"
STEVE_SKIN_URL = ("http://textures.minecraft.net/texture/d5c4ee5ce20aed9e33e866c66"
              "caa37178606234b3721084bf01d13320fb2eb3f")

# UI stuff
CHECKMARK_DELAY = 1500 # milliseconds