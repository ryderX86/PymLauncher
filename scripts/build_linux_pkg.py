import logging

from minecraftlauncher import constants

log = logging.getLogger(__name__)

# epoch is and should remain unused
# if constants.LAUNCHER_VERSION.startswith("build"):
#     epoch = constants.LAUNCHER_VERSION.split("-")[1]
#     if not epoch.isdecimal():
#         raise TypeError(
#             f"Invalid launcher version: {constants.LAUNCHER_VERSION}"
#         )
#     epoch_txt = f"epoch={epoch}"
# else:
#     epoch_txt = ""

run_makepkg = True
match constants.ARCH:
    case "x86_64" | "arm64":
        arch = constants.ARCH
    case "x86":
        arch = "i686"
    case _:
        log.warning(
            "Unknown architecture: '%s', won't automatically run makepkg.",
            constants.ARCH,
        )
        arch = "any"
        run_makepkg = False

PKGBASE = f"""
pkgname={constants.LAUNCHER_NAME}
pkgver={constants.LAUNCHER_VERSION.replace("-", "")}
pkgdesc='Simple Open-Source Launcher for Minecraft'
arch={constants.ARCH}
license=('BSD-3-Clause' 'LGPL-3.0-only')
url='https://github.com/{constants.AUTHOR_USR}/{constants.LAUNCHER_NAME}'
makedepends=('python>=3.11')
depends=()
optdepends=('gnome-keyring', 'libsecret', 'kwallet')
build() {{}}
package()
{{
}}
"""
