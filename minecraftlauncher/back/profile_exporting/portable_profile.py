from pathlib import Path
from enum import IntEnum, StrEnum
import zipfile
import logging
import json
import glob
import os

from minecraftlauncher.datatypes.launch_profile import GameProfile
from minecraftlauncher.functions import is_path_valid
from minecraftlauncher.back import profile_manager
from minecraftlauncher import constants, args

log = logging.getLogger(__name__)
if args.exporting_debug:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.INFO)


def pack_file(path: Path, stop_at: Path, zipf: zipfile.ZipFile):
    """
    Add files deep into an archive without having to parse the directory every
    single time.
    """
    if path.is_file():
        file = path.resolve()
        path = path.parent
    else:
        file = None
    path = path.resolve()
    # include the creation of the base folder:
    stop_at = stop_at.parent.resolve()
    if str(stop_at) not in str(path):
        raise ValueError("Paths must match at beginning!")
    dest_dir = str(path).replace(str(stop_at), "")
    while dest_dir.startswith(constants.OS_PATH_DELIM):
        dest_dir = dest_dir[1:]
    if file:
        try:
            zipf.write(file, dest_dir + "/" + file.name)
        except Exception as err:
            err.add_note(f'File at "{str(file)}" caused the above error.')
            raise
    return dest_dir


class ExportType(StrEnum):
    DEFAULT = "default"
    MODRINTH = "modrinth"


class PortableProfile:
    class PathType(IntEnum):
        DIR = 0
        FILE = 1

    type ExportType = ExportType

    def __init__(self, prof: GameProfile | str):
        match prof:
            case str():
                self._prof = prof
            case GameProfile():
                self._prof = prof.uuid

    @property
    def base(self):
        game_dir = self.prof.game_dir
        if game_dir:
            return Path(game_dir)
        return constants.MINECRAFT_DIR

    def _dir_exists(self, directory: str):
        if constants.OS_PATH_DELIM in directory:
            return False
        path = os.path.join(self.base, directory)
        if os.path.isdir(path):
            # only return true if it's not a blank dir
            if os.path.isdir(path) and [*glob.glob(f"{path}/*")]:
                return True
        return False

    def _dirs_exist(self, dirs: list[str]) -> list[str] | bool:
        existing_dirs = []
        b = self.base
        for d in dirs:
            p = os.path.join(b, d)
            if os.path.isfile(p):
                existing_dirs.append(p)
            elif os.path.isdir(p) and [*glob.glob(f"{p}/*")]:
                existing_dirs.append(p)
        if existing_dirs:
            return existing_dirs
        return False

    @property
    def prof(self):
        return profile_manager.get_profile(self._prof)

    @property
    def mods(self):
        return self._dir_exists("mods")

    @property
    def options_txt(self):
        return self._dir_exists("options.txt")

    @property
    def resource_packs(self):
        return self._dir_exists("resourcepacks") or self._dir_exists(
            "texturepacks"
        )

    @property
    def saves(self):
        return self._dir_exists("saves")

    @property
    def quick_play(self):
        return self._dir_exists("launcher_quick_play.json")

    @property
    def screenshots(self):
        return self._dir_exists("screenshots")

    @property
    def versions(self):
        return self._dir_exists("versions")

    @property
    def config(self):
        return self._dir_exists("config")

    @property
    def menuworlds(self):
        return self._dir_exists("menuworlds")

    @property
    def debug_profile(self):
        return self._dir_exists("debug-profile.json")

    def _get_version_paths(self) -> list[Path]:
        pathlist = []
        versions_folder = os.path.join(constants.MINECRAFT_DIR, "versions")
        for path in glob.glob(f"{versions_folder}/**/*.json"):
            if os.path.split(path)[0] == versions_folder:
                continue
            with open(path, "r") as f:
                txt = f.read()
            try:
                v_json = json.loads(txt)
            except json.JSONDecodeError as err:
                log.error("Failed reading JSON:", exc_info=err)
            else:
                if v_json.get("downloads", {}).get("client", {}).get("url"):
                    pathlist.append(path)
        return pathlist

    @classmethod
    def import_profile(
        cls, file: str | Path, target_dir: str | Path, overwrite: bool = False
    ):
        if isinstance(file, Path):
            file = str(file)
        if not os.path.isfile(file):
            raise FileNotFoundError(file)
        if isinstance(target_dir, Path):
            target_dir = str(target_dir)
        if not os.path.isdir(target_dir):
            if not is_path_valid(target_dir):
                raise ValueError(f"Invalid file path: {target_dir}")
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as err:
                raise ValueError(
                    f"Failed to make directory at {target_dir!r}; "
                    "do we have permissions?"
                ) from err

        with zipfile.ZipFile(file, "r") as zipf:
            filenames = [f.filename for f in zipf.filelist]
            if "profile.json" not in filenames:
                return False
            profile_json_raw = zipf.open("profile.json").read().decode()
            try:
                profile_json = json.loads(profile_json_raw)
            except json.JSONDecodeError as err:
                log.error(
                    "Failed to decode JSON in portable profile:", exc_info=err
                )
                zipf.close()
                return False
            match profile_json.get("_FORMAT", "?"):
                case "beachhorse":
                    cls.import_beachhorse(
                        profile_json, zipf, target_dir, overwrite
                    )
                    return
                case _:
                    raise ValueError(
                        f"Unknown format: {profile_json.get("_FORMAT", "unidentified format")}"
                    )

    @classmethod
    def import_beachhorse(
        cls,
        profile_info: dict,
        zipf: zipfile.ZipFile,
        target_dir: str,
        overwrite: bool,
    ):
        ...
        # filenames = [f.filename for f in zip.filelist]
        # for path in profile_info["_PATHS"]:
        #     match path[0]:
        #         case "?":
        #             OPTIONAL = True
        #             path = path[1:]
        #         case _:
        #             OPTIONAL = False
        #     IS_FILE = "." in path

        #     if path not in filenames:
        #         if OPTIONAL:
        #             log.debug(
        #                 "skipping filepath '%s' since it's optional and "
        #                 "wasn't found" % path)
        #             continue
        #         else:
        #             raise FileNotFoundError(path)

        #     p = target_dir / path
        #     if p.exists() and (p.is_file() or p.is_dir()) and not overwrite:
        #             zip.close()
        #             raise FileExistsError(str(p))
        #     elif p.exists() and (p.is_file() or p.is_dir()):
        #         log.debug("Overwriting '%s'" % str(p))
        #     if IS_FILE:
        #         zip.extract(path, p)
        #     else:
        #         zip.filelist

    def export_beachhorse(
        self,
        output: str | os.PathLike,
        mods: bool,
        options_txt: bool,
        resource_packs: bool,
        saves: bool,
        screenshots: bool,
        versions: bool,
        config: bool,
        coremods: bool,
        menuworlds: bool,
        debug_profile: bool,
    ):
        b = self.base

        if isinstance(output, Path):
            output = str(output)
        if not os.path.isdir(os.path.split(output)[0]):
            raise ValueError("Output path with no parent!")

        if os.path.isfile(output):
            log.warning("Overriding fp object at '%s'", str(output))
            os.unlink(output)

        if os.path.splitext(output)[-1] == ".json":
            with open(output, "w") as f:
                f.write(json.dumps(self.prof.to_dict_compat()))
            return True

        log.debug('Opening "%s" as NEW archive', str(output))
        with zipfile.ZipFile(output, "x", zipfile.ZIP_ZSTANDARD) as zipf:
            if mods and self.mods:
                p = b / "mods"
                zipf.mkdir("mods")
                log.info('Taking mods from "%s"', str(p))
                mod_list = [*p.rglob("*.jar"), *p.rglob("*.zip")]
                if (b / "coremods").exists() and coremods:
                    cm = b / "coremods"
                    mod_list.extend([*cm.rglob("*.zip"), *cm.rglob("*.jar")])
                for mod in [*p.rglob("*.jar"), *p.rglob("*.zip")]:
                    mod = mod.resolve()
                    if mod.parent != p:
                        try:
                            pack_file(mod, p, zipf)
                        except Exception as err:
                            err.add_note(
                                f'ZIP file open at time of exception: "{str(output)}"'
                            )
                            raise
                        arc = f"mods/{mod.parent}/{mod.name}"
                    else:
                        arc = f"mods/{mod.name}"
                    log.debug("Adding '%s' to archive>/%s", str(mod), arc)
                    zipf.write(mod, arc)

            if options_txt and self.options_txt:
                log.info("Including options.txt")
                zipf.write(b / "options.txt", "options.txt")

            if resource_packs and self.resource_packs:
                p = b / "resourcepacks"
                if p.exists():
                    zipf.mkdir("resourcepacks")
                else:
                    p = b / "texturepacks"
                    zipf.mkdir("texturepacks")
                log.info("Taking resource packs from '%s'", str(p))
                for pack in [*p.glob("*")]:
                    if pack.is_file():
                        if pack.suffix != ".zip":
                            continue
                        zipf.write(pack, f"{p.name}/{pack.name}")
                    elif pack.is_dir():
                        if not (pack / "pack.mcmeta").exists():
                            continue
                        zipf.mkdir(f"{p.name}/{pack.name}")
                        for path in pack.rglob("*"):
                            pack_file(path, p, zipf)

            if saves and self.saves:
                p = b / "saves"
                log.info("Taking save files from '%s'", str(p))
                zipf.mkdir("saves")
                for file in p.rglob("*"):
                    pack_file(file, p, zipf)

            if screenshots and self.screenshots:
                p = b / "screenshots"
                log.info("Taking screenshots from '%s'", str(p))
                zipf.mkdir("screenshots")
                for file in p.glob("*.png"):
                    zipf.write(file, f"screenshots/{file.name}")

            if versions and self.versions:
                log.info("Including versions")
                p = b / "versions"
                for file in p.rglob("*.json"):
                    if file.parent == p:
                        continue
                    elif file.parent.name != file.stem:
                        continue
                    pack_file(file, p, zipf)

            if config and self.config:
                log.info("Including mod config files")
                p = b / "config"
                for file in p.rglob("*"):
                    pack_file(file, p, zipf)

            if menuworlds and self.menuworlds:
                log.info("Including menuworlds mod data")
                p = b / "menuworlds"
                for file in p.rglob("*"):
                    pack_file(file, p, zipf)

            if debug_profile and self.debug_profile:
                log.info("Including debug (F3) profile")
                zipf.write(b / "debug-profile.json", "debug-profile.json")

            profile_dump = self.prof.to_dict()
            profile_dump["_FORMAT"] = "beachhorse"
            profile_dump["_PATHS"] = []
            if mods:
                profile_dump["_PATHS"].append("mods")
            if options_txt:
                profile_dump["_PATHS"].append("options.txt")
            if resource_packs:
                profile_dump["_PATHS"].append("?resourcepacks")
                profile_dump["_PATHS"].append("?texturepacks")
            if saves:
                profile_dump["_PATHS"].append("saves")
            if screenshots:
                profile_dump["_PATHS"].append("screenshots")
            if versions:
                profile_dump["_PATHS"].append("versions")
            if config:
                profile_dump["_PATHS"].append("config")
            if coremods:
                profile_dump["_PATHS"].append("coremods")
            if menuworlds:
                profile_dump["_PATHS"].append("menuworlds")
            if debug_profile:
                profile_dump["_PATHS"].append("debug_profile.json")
            profile_json = json.dumps(profile_dump)
            zipf.writestr("profile.json", profile_json)

            zipf.close()

        return True

    def export(
        self,
        type_: ExportType,
        output: str | Path,
        mods: bool,
        options_txt: bool,
        resource_packs: bool,
        saves: bool,
        screenshots: bool,
        versions: bool,
        config: bool,
        coremods: bool,
        menuworlds: bool,
        debug_profile: bool,
    ):
        match type_:
            case ExportType.DEFAULT:
                return self.export_beachhorse(
                    output,
                    mods,
                    options_txt,
                    resource_packs,
                    saves,
                    screenshots,
                    versions,
                    config,
                    coremods,
                    menuworlds,
                    debug_profile,
                )
            # case ExportType.MODRINTH:
            #     return self.export_modrinth(
            #         output, mods, options_txt, resource_packs, saves,
            #         screenshots, versions, config, coremods, menuworlds,
            #         debug_profile
            #     )
