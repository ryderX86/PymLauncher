from pathlib import Path
from enum import IntEnum
import json
import os
import zipfile
import logging

from minecraftlauncher.datatypes.GameProfile import GameProfile
from minecraftlauncher.back import profile_manager
from minecraftlauncher import constants

log = logging.getLogger(__name__)

def recursive_add_dir(path:Path, stop_at:Path, zip:zipfile.ZipFile):
    """
    Recursively add directories to a ZIP file. Returns the final path of the
    nested folders.
    """
    def try_make_folder(f:str):
        try:
            zip.mkdir(f)
        except FileExistsError:
            log.warning("Threw an error since folder exists! Ignoring...")
            return False
        except Exception as err:
            err.add_note("ZIP file error for %s" % f)
            raise
        else:
            return True
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
    folders = str(path).replace(str(stop_at), "")
    while folders.startswith(constants.OS_PATH_DELIM):
        log.debug("\"%s\" -> \"%s\"" % (folders, folders[1:]))
        folders = folders[1:]
    folder_list = folders.split(constants.OS_PATH_DELIM)
    try_make_folder(folder_list[0])
    last_folder = folder_list[0]
    for folder in folder_list[1:]:
        last_folder = last_folder + f"/{folder}"
        try_make_folder(last_folder)
    if file:
        try:
            zip.write(file, folders)
        except Exception as err:
            err.add_note("File at \"%s\" caused the above error." % str(file))
            raise
    return folders
    

class PortableProfile:
    class PathType(IntEnum):
        DIR = 0
        FILE = 1
    def __init__(self, prof:GameProfile|str, mods:bool,
                 options_txt:bool, resource_packs:bool, saves:bool,
                 quick_play:bool, screenshots:bool, versions:bool, config:bool,
                 coremods:bool, menuworlds:bool, debug_profile:bool,
                 limit_resource_packs:list[str]=[], limit_saves:list[str]=[],
                 limit_screenshots:list[str]=[],
                 limit_menuworlds:list[str]=[]):
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

    def _dir_exists(self, dir:str):
        if constants.OS_PATH_DELIM in dir:
            return False
        path = self.base / dir
        if path.exists():
            # only return true if it's not a blank dir
            if path.is_file() or (path.is_dir() and [*path.glob("*")]):
                return True
        return False
    
    def _dirs_exist(self, dirs:list[str]) -> list[str]|bool:
        existing_dirs = []
        b = self.base
        for d in dirs:
            p = b / d
            if p.exists():
                if p.is_file():
                    existing_dirs.append(p)
                elif p.is_dir() and [*p.glob("*")]:
                    existing_dirs.append(p)
        if existing_dirs:
            return existing_dirs
        return False

    @property
    def prof(self):
        return profile_manager.get_profile(self._prof)
    
    @property
    def mods(self):
        return self._dirs_exist(["mods", "coremods"])
    
    @property
    def options_txt(self):
        return self._dir_exists("options.txt")
    
    @property
    def resource_packs(self):
        return (self._dir_exists("resourcepacks")
                or self._dir_exists("texturepacks"))
    
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
        versions_folder = constants.MINECRAFT_DIR / "versions"
        for path in versions_folder.glob("**/*.json"):
            if path.parent == versions_folder:
                continue
            try:
                v_json = json.loads(path.read_text())
            except json.JSONDecodeError as err:
                log.error("Failed reading JSON:", exc_info=err)
            else:
                if v_json.get("downloads", {}).get("client", {}).get("url"):
                    pathlist.append(path)
        return pathlist
    
    def export(self, output:str|Path, mods:bool, options_txt:bool,
               resource_packs:bool, saves:bool, quick_play:bool,
               screenshots:bool, versions:bool, config:bool, coremods:bool,
               menuworlds:bool, debug_profile:bool):
        b = self.base

        if isinstance(output, str):
            output = Path(output)
        if not output.parent.exists():
            raise ValueError("Output path with no parent!")
        
        if output.exists():
            log.warning("Overriding fp object at '%s'" % str(output))
            output.unlink()

        if output.suffix == ".json":
            output.write_text(json.dumps(self.prof.to_dict_compat()))
            return True
        
        log.debug("Opening \"%s\" as NEW archive" % str(output))
        with zipfile.ZipFile(output, "x") as zip:
            if mods and self.mods:
                p = b / "mods"
                zip.mkdir("mods")
                log.info("Taking mods from \"%s\"" % str(p))
                mod_list = [*p.rglob("*.jar"), *p.rglob("*.zip")]
                if (b / "coremods").exists() and coremods:
                    cm = b / "coremods"
                    mod_list.extend([*cm.rglob("*.zip"), *cm.rglob("*.jar")])
                for mod in [*p.rglob("*.jar"), *p.rglob("*.zip")]:
                    mod = mod.resolve()
                    if mod.parent != p:
                        try:
                            recursive_add_dir(mod, p, zip)
                        except Exception as err:
                            err.add_note(
                                "ZIP file open at time of exception: \"%s\""
                                % str(output)
                            )
                            raise
                        arc = f"mods/{mod.parent}/{mod.name}"
                    else:
                        arc = f"mods/{mod.name}"
                    log.debug("Adding '%s' to archive>/%s" % (str(mod), arc))
                    zip.write(mod, arc)

            if options_txt and self.options_txt:
                log.info("Including options.txt")
                zip.write(b / "options.txt", "options.txt")
            
            if resource_packs and self.resource_packs:
                p = b / "resourcepacks"
                if p.exists():
                    zip.mkdir("resourcepacks")
                else:
                    p = b / "texturepacks"
                    zip.mkdir("texturepacks")
                log.info("Taking resource packs from \"%s\"" % str(p))
                for pack in [*p.glob("*")]:
                    if pack.is_file():
                        if pack.suffix != ".zip":
                            continue
                        zip.write(pack, "%s/%s" % (p.name, pack.name))
                    elif pack.is_dir():
                        if not (pack / "pack.mcmeta").exists():
                            continue
                        zip.mkdir("%s/%s" % (p.name, pack.name))
                        for path in pack.rglob("*"):
                            recursive_add_dir(path, p, zip)
            
            if saves and self.saves:
                p = b / "saves"
                log.info("Taking save files from '%s'" % str(p))
                zip.mkdir("saves")
                for file in p.rglob("*"):
                    recursive_add_dir(file, p, zip)

            if quick_play and self.quick_play:
                log.info("Including launcher_quick_play.json")
                zip.write(b / "launcher_quick_play.json",
                          "launcher_quick_play.json")
            
            if screenshots and self.screenshots:
                p = b / "screenshots"
                log.info("Taking screenshots from '%s'" % str(p))
                zip.mkdir("screenshots")
                for file in p.glob("*.png"):
                    zip.write(file, "screenshots/%s" % file.name)
            
            if versions and self.versions:
                log.info("Including versions")
                p = b / "versions"
                for file in p.rglob("*.json"):
                    if file.parent == p:
                        continue
                    recursive_add_dir(file, p, zip)
            
            if config and self.config:
                log.info("Including mod config files")
                p = b / "config"
                for file in p.rglob("*"):
                    recursive_add_dir(file, p, zip)
            
            if menuworlds and self.menuworlds:
                log.info("Including menuworlds mod data")
                p = b / "menuworlds"
                for file in p.rglob("*"):
                    recursive_add_dir(file, p, zip)
            
            if debug_profile and self.debug_profile:
                log.info("Including debug (F3) profile")
                zip.write(b / "debug-profile.json", "debug-profile.json")
            
            zip.close()

        