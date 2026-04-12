"""
minecraftlauncher.back.game_launcher

Builds the launch command for Minecraft, performs argument-template
substitution, and starts the game process.
"""
from pathlib import Path
from time import sleep
import logging
import os
import sys
import subprocess
import platform
import uuid

from minecraftlauncher.constants import (
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    MINECRAFT_DIR,
    OS,
    CLASSPATH_SEPARATOR,
    DEFAULT_JVM_ARGS
)
from minecraftlauncher.back.library_manager import _evaluate_rules
from .library_manager import build_classpath, filter_libraries
from .java_manager import find_java_exc

log = logging.getLogger(__name__)

def _substitute(template:str, values:dict[str, str]):
    """Replace `${key}` placeholder in `template` with values from `values`"""
    result = template
    for key, val in values.items():
        result = result.replace("${%s}" % key, str(val))
    return result.strip()

def _process_jvm_arg_entry(entry, values:dict[str, str]):
    """
    Process an element from the JVM arguments list.

    Entries can be plain strings or dicts with `rules` and `value`.

    `values` is used to replace templates in the arguments.
    """
    if isinstance(entry, str):
        return [_substitute(entry, values)]
    elif isinstance(entry, dict):
        rules = entry.get("rules", [])
        if not _evaluate_rules(rules):
            return []
        value = entry.get("value", [])
        if isinstance(value, str):
            return [_substitute(value, values)]
        elif isinstance(value, list):
            return [_substitute(v, values) for v in value if v]
        else:
            log.warning("Unexpected argument value type: '%s'"
                        % type(value).__name__)
    elif isinstance(entry, list):
        return [_substitute(v, values) for v in entry]

    log.warning("Unexpected argument type: '%s'" % type(entry).__name__)
    return []

def _process_arg_entry(entry, values:dict[str, str], features:list[str]):
    """
    Process an element from the game arguments list.

    Entries can be strings or dicts with `rules` and `value`.

    `values` is used to replace templates in the arguments, while `features` is
    used to determine rule outcomes.

    When multiple rules are present, only one `"allow"`/`True` combo are
    required to add the argument to the final launch args.
    """
    if isinstance(entry, str):
        return _substitute(entry, values)
    elif isinstance(entry, dict):
        allowed = False
        for rule in entry.get("rules", []):
            action = rule.get("action") == "allow"
            features_present = False
            for feature in features:
                if feature in rule.get("features", {}).keys():
                    features_present = True
            if features_present == action:
                allowed = True
        if len(entry.get("rules", [])) < 1:
            # just in case
            allowed = True
        value = entry.get("value", [])
        if not allowed:
            return ""
        elif not value:
            return ""
        elif isinstance(value, str):
            return _substitute(value, values)
        elif isinstance(value, list):
            return " ".join([_substitute(v, values) for v in value if v])
        else:
            log.warning("Skipping unexpected entry value type: '%s'"
                        % type(value).__name__)
    elif isinstance(entry, list):
        return " ".join([_substitute(v, values) for v in entry])
    else:
        log.warning("Skipping unexpected entry type: '%s'"
                    % type(entry).__name__)
    return ""

def _build_args(version_json:dict, values:dict[str, str], features:list[str]):
    """Builds JVM and game args. Returns a tuple in order of `(jvm, game)`"""
    args = version_json.get("arguments", {})

    jvm_args = []
    for entry in args.get("jvm", []):
        added_args = _process_jvm_arg_entry(entry, values)
        if added_args:
            jvm_args.extend(added_args)

    # new since 26.1
    # for entry in args.get("default-user-jvm", []):
    #     jvm_args.extend(_process_jvm_arg_entry(entry, values))
    
    game_args = []
    for entry in args.get("game", []):
        added_args = _process_arg_entry(entry, values, features)
        if added_args:
            game_args.append(added_args)

    return jvm_args, game_args

def _build_legacy_args(version_json:dict, values:dict[str, str],
                       features:list[str]):
    """Builds JVM and game args. Returns a tuple in order of `(jvm, game)`"""
    raw_game_args:str = version_json.get(
        "minecraftArguments",
        "--username ${auth_player_name} --session ${auth_session} "
        "--versionName ${version_name} "
        "--accessToken ${auth_access_token} --gameDir ${game_directory} "
        "--assetsDir ${assets_root} --userProperties {} "
        "--userType msa"
    )
    game_args = [_substitute(arg, values) for arg in raw_game_args.split()]

    jar_path = MINECRAFT_DIR / "versions" / version_json["id"] / f"{version_json["id"]}.jar"

    default_jvm_args = [
        f"-Djava.library.path={values.get("natives_directory", "")}",
        f"-Dminecraft.launcher.brand={LAUNCHER_NAME}",
        f"-Dminecraft.launcher.version={LAUNCHER_VERSION}",
        f"-Dminecraft.client.jar={jar_path}",
        "-cp", values.get("classpath", ""),
    ]

    return default_jvm_args, game_args

def default_user_jvm_args_factory(version_json:dict):
    args = version_json.get("arguments", {})
    if args.get("default-user-jvm", []):
        jvm_args = []
        for arg in args["default-user-jvm"]:
            if arg.get("rules", []):
                if not _evaluate_rules(arg["rules"]):
                    continue
            match arg["value"]:
                case str():
                    jvm_args.append(arg["value"])
                case list():
                    for text in arg["value"]:
                        if text.startswith("-Xms"):
                            continue
                        elif text.startswith("-Xmx"):
                            continue
                        else:
                            jvm_args.append(text)
                case _:
                    raise TypeError("Expected list or str, got %s"
                                    % type(arg["value"].__name__))
        # mojang is very interesting at making decisions regarding their
        # manifest files
        # if "-XX:UseZGC" in jvm_args and "-XX:UseG1GC" in jvm_args:
        #     i = jvm_args.index("-XX:UseG1GC")
        #     del jvm_args[i]
        return " ".join(jvm_args)
    return DEFAULT_JVM_ARGS

def build_launch_command(version_json:dict, player_name:str, player_uuid:str,
                         player_auth_token:str, player_type:str, demo:bool,
                         xuid:str|None=None, java_path:str|None=None,
                         log4j_config:str|None=None, classpath:str|None=None,
                         game_dir:str|None=None, prof_jvm_args:str|None=None,
                         memory_min:str|None=None, memory_max:str|None=None,
                         resolution_width:int|None=None,
                         resolution_height:int|None=None,
                         mods_folder:str|None=None,
                         mods_folder_mode:str|None=None, **kwargs):
    """
    Builds the full command to launch the game.
    
    Returns a list suitable for `subprocess.Popen`.
    """
    version_id:str = version_json.get("id", "")
    if not version_id:
        raise ValueError("'version_json' missing expected value for 'id'")
    
    if not java_path:
        java_info = version_json.get("javaVersion", {})
        needed_java_version = java_info.get("component", "")
        java_path = str(find_java_exc(needed_java_version))
    
    jar_path = MINECRAFT_DIR / "versions" / version_id / f"{version_id}.jar"
    
    asset_index_id = version_json.get("assetIndex", {}).get("id")
    if not asset_index_id:
        asset_index_id = version_json.get("assets")
    if not asset_index_id:
        raise ValueError("'version_json' missing expected value for 'assets'"
                         " or 'assetsIndex'")
    
    if game_dir and not os.path.isdir(game_dir):
        try:
            Path(game_dir).resolve().mkdir(parents=True, exist_ok=True)
        except Exception as err:
            raise ValueError("'game_dir' value '%s' is an invalid path"
                             % game_dir) from err
    else:
        game_dir = str(MINECRAFT_DIR)

    natives_dir = MINECRAFT_DIR / "bin" / version_id
    if not (natives_dir.exists() and natives_dir.is_dir()):
        natives_dir.mkdir(parents=True, exist_ok=True)

    if not classpath:
        lib_list = filter_libraries(version_json)
        classpath = build_classpath(lib_list, jar_path)

    if resolution_height and not resolution_width:
        resolution_width = 1024
    if resolution_width and not resolution_height:
        resolution_height = 768
    
    values = {
        "auth_player_name": player_name,
        "auth_uuid": player_uuid,
        "version_name": version_id,
        "version_type": version_json.get("type", "unknown"),
        "auth_access_token": player_auth_token,
        "auth_session": f"token:{player_auth_token}:{player_uuid}",
        "user_properties": "{}",
        "user_type": "msa",
        "assets_index_name": asset_index_id,
        "game_assets": str(MINECRAFT_DIR / "assets" / "virtual" / "legacy"),
        "assets_root": str(MINECRAFT_DIR / "assets"),
        "game_directory": game_dir,
        "clientid": "0",
        "auth_xuid": xuid,
        "resolution_width": resolution_width,
        "resolution_height": resolution_height,
        "natives_directory": str(natives_dir),
        "classpath": classpath,
        "library_directory": str(MINECRAFT_DIR / "libraries"),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "jar_path": str(jar_path),
        **kwargs
    }

    features:list[str] = []
    if resolution_height or resolution_width:
        features.append("has_custom_resolution")
    if demo:
        features.append("is_demo_user")
    
    if "arguments" in version_json.keys():
        jvm_args, game_args = _build_args(version_json, values, features)
    else:
        jvm_args, game_args = _build_legacy_args(version_json, values,
                                                 features)
        
    if mods_folder:
        if " " in mods_folder:
            if mods_folder[0] != '"' or mods_folder[-1] != '"':
                mods_folder = f'"{mods_folder.strip('"')}"'
        if not mods_folder_mode:
            mods_folder_mode = "modsFolder"
        jvm_args.insert(-2, "-Dfabric.%s=%s" % (mods_folder_mode, mods_folder))
    
    cmd:list[str] = [java_path]

    if OS == "windows":
        cmd.extend(
            ["-Dos.name=Windows 10", "-Dos.version=10.0"]
        )

    cmd.extend(jvm_args)
    if log4j_config:
        cmd.append(log4j_config)
    
    main_class = version_json.get("mainClass",
                                  "net.minecraft.client.main.Main")
    cmd.extend([f"-Xms{memory_min}", f"-Xmx{memory_max}"])
    if prof_jvm_args:
        cmd.extend(prof_jvm_args.split(" "))
    cmd.append(main_class)
    cmd.extend(game_args)
    
    if resolution_width and resolution_height and "--width" not in cmd:
        cmd.extend(["--width", str(resolution_width)])
    if resolution_width and resolution_height and "--height" not in cmd:
        cmd.extend(["--height", str(resolution_height)])

    return cmd

def launch_game(command:list[str], cwd:str|Path|None):
    if not cwd:
        cwd = MINECRAFT_DIR
    
    log.info("Launching Minecraft")
    kwargs = {}
    if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1
        kwargs["startupinfo"] = si
    
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        universal_newlines=True,
        bufsize=1,
        **kwargs
    )
    log.info("Minecraft started; PID: %d" % process.pid)
    return process