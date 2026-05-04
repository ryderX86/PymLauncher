"""
minecraftlauncher.back.game_launcher

Builds the launch command for Minecraft, performs argument-template
substitution, and starts the game process.
"""

from collections.abc import Callable
from string import Template
from pathlib import Path
import logging
import os
import subprocess

from PySide6.QtCore import QThread, Signal
import requests

from minecraftlauncher.constants import (
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    MINECRAFT_DIR,
    OS,
    DEV,
    offline_mode,
)
from minecraftlauncher.front.window import (
    WarningDialog,
    WarningType,
    ButtonConfig,
)
from minecraftlauncher.datatypes import GameProfile
from minecraftlauncher.back.library_manager import evaluate_rules
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher import config
from .library_manager import build_classpath, filter_libraries
from .java_manager import find_java_exc
from . import (
    version_manager,
    asset_manager,
    library_manager,
    java_manager,
    account_manager,
)

log = logging.getLogger(__name__)


def _substitute(template: str, values: dict[str, str]):
    values = {k: v for k, v in values.items() if v is not None}
    t = Template(template)
    subbed = t.safe_substitute(values)
    # unfrozen only so auth tokens don't get leaked into logs when built:
    if DEV and "${" in subbed:
        log.warning("Unsubstituted template leftover in string: '%s'", subbed)
    return subbed


def _process_jvm_arg_entry(entry, values: dict[str, str]) -> list[str]:
    """
    Process an element from the JVM arguments list.

    Entries can be plain strings or dicts with `rules` and `value`.

    `values` is used to replace templates in the arguments.
    """
    if isinstance(entry, str):
        return [_substitute(entry, values)]
    elif isinstance(entry, dict):
        rules = entry.get("rules", [])
        if not evaluate_rules(rules):
            return []
        value = entry.get("value", [])
        if isinstance(value, str):
            return [_substitute(value, values)]
        elif isinstance(value, list):
            return [_substitute(v, values) for v in value if v]
        else:
            log.warning(
                "Unexpected argument value type: '%s'", type(value).__name__
            )
    elif isinstance(entry, list):
        return [_substitute(v, values) for v in entry]

    log.warning("Unexpected argument type: '%s'", type(entry).__name__)
    return []


def _process_arg_entry(entry, values: dict[str, str], features: list[str]):
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
            log.warning(
                "Skipping unexpected entry value type: '%s'",
                type(value).__name__,
            )
    elif isinstance(entry, list):
        return " ".join([_substitute(v, values) for v in entry])
    else:
        log.warning(
            "Skipping unexpected entry type: '%s'", type(entry).__name__
        )
    return ""


def _build_args(
    version_json: dict, values: dict[str, str], features: list[str]
):
    """Builds JVM and game args. Returns a tuple in order of `(jvm, game)`"""
    args = version_json.get("arguments", {})

    jvm_args: list[str] = []
    for entry in args.get("jvm", []):
        added_args = _process_jvm_arg_entry(entry, values)
        if added_args:
            jvm_args.extend(added_args)

    # new since 26.1
    # for entry in args.get("default-user-jvm", []):
    #     jvm_args.extend(_process_jvm_arg_entry(entry, values))

    game_args: list[str] = []
    for entry in args.get("game", []):
        added_args = _process_arg_entry(entry, values, features)
        if added_args:
            game_args.append(added_args)

    return jvm_args, game_args


def _build_legacy_args(
    version_json: dict, values: dict[str, str], features: list[str]
):
    """Builds JVM and game args. Returns a tuple in order of `(jvm, game)`"""
    raw_game_args: str = version_json.get(
        "minecraftArguments",
        "--username ${auth_player_name} --session ${auth_session} "
        "--versionName ${version_name} "
        "--accessToken ${auth_access_token} --gameDir ${game_directory} "
        "--assetsDir ${assets_root} --userProperties {} "
        "--userType msa",
    )
    game_args = _substitute(raw_game_args, values).split()

    jar_path = (
        MINECRAFT_DIR
        / "versions"
        / version_json["id"]
        / f"{version_json["id"]}.jar"
    )

    default_jvm_args = [
        f"-Djava.library.path={values["natives_directory"]}",
        f"-Dminecraft.launcher.brand={LAUNCHER_NAME}",
        f"-Dminecraft.launcher.version={LAUNCHER_VERSION}",
        f"-Dminecraft.client.jar={jar_path}",
        "-cp",
        values["classpath"],
    ]

    return default_jvm_args, game_args


def build_launch_command(
    version_json: dict,
    player_name: str,
    player_uuid: str,
    player_auth_token: str,
    player_type: str,
    demo: bool,
    xuid: str | None = None,
    java_path: str | None = None,
    log4j_config: str | None = None,
    classpath: str | None = None,
    game_dir: str | None = None,
    prof_jvm_args: str | None = None,
    memory_min: str | None = None,
    memory_max: str | None = None,
    resolution_width: int | None = None,
    resolution_height: int | None = None,
    mods_folder: str | None = None,
    mods_folder_mode: str | None = None,
    **kwargs,
):
    """
    Builds the full command to launch the game.

    Returns a list suitable for `subprocess.Popen`.
    """
    version_id: str = version_json.get("id", "")
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
        raise ValueError(
            "'version_json' missing expected value for 'assets'"
            " or 'assetsIndex'"
        )

    if game_dir:
        if not os.path.isdir(game_dir):
            try:
                Path(game_dir).resolve().mkdir(parents=True, exist_ok=True)
            except Exception as err:
                raise ValueError(
                    f"'game_dir' value '{game_dir}' is an invalid path"
                ) from err
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
        **kwargs,
    }

    features: list[str] = []
    if resolution_height or resolution_width:
        features.append("has_custom_resolution")
    if demo:
        features.append("is_demo_user")

    if "arguments" in version_json.keys():
        jvm_args, game_args = _build_args(version_json, values, features)
    else:
        jvm_args, game_args = _build_legacy_args(version_json, values, features)

    if mods_folder:
        if " " in mods_folder:
            if mods_folder[0] != '"' or mods_folder[-1] != '"':
                mods_folder = f'"{mods_folder.strip('"')}"'
        if not mods_folder_mode:
            mods_folder_mode = "modsFolder"
        jvm_args.insert(-2, f"-Dfabric.{mods_folder_mode}={mods_folder}")

    cmd: list[str] = [java_path]

    if OS == "windows":
        cmd.extend(["-Dos.name=Windows 10", "-Dos.version=10.0"])

    cmd.extend(jvm_args)
    if log4j_config:
        cmd.append(log4j_config)

    main_class = version_json.get("mainClass", "net.minecraft.client.main.Main")
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


def launch_game(command: list[str], cwd: str | Path | None):
    if not cwd:
        cwd = MINECRAFT_DIR

    log.info("Launching Minecraft")
    kwargs = {}

    if OS == "windows":
        si = subprocess.STARTUPINFO()  # type: ignore
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore
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
        **kwargs,
    )
    log.info("Minecraft started; PID: %d", process.pid)
    return process


class LaunchWorker(QThread):
    """Background worker for downloading game files and launching."""

    progress = Signal(
        str, float, float, bool
    )  # step label, current, total, is mb
    finished = Signal(bool, str)  # successful, message
    status = Signal(str)  # status text
    game_closed = Signal(str, str)
    game_log = Signal(str)
    """
    `[0]` (`int`) - Exit code<br>
    `[1]` (`str`) - stdout<br>
    `[2]` (`str`) - stderr
    """

    log = log.getChild("LaunchWorker")

    def __init__(
        self,
        version_id: str,
        profile_data: GameProfile,
        auth_info: LauncherAccount,
        emit_logs: bool = True,
        log_hook: Callable[[str], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.version_id = version_id
        self.profile_data = profile_data
        self.auth_info = auth_info
        self._hook = log_hook
        self.emit_logs = emit_logs
        self._p: subprocess.Popen

    def run(self):
        if offline_mode:
            allow_run = WarningDialog.warn(
                self,
                "Launch in offline mode?",
                "Offline mode is experimental. Do you want to continue?",
                WarningType.OFFLINE_MODE_LAUNCH,
                button_config=ButtonConfig.YES_NO,
            )
            if not allow_run:
                self.finished.emit(False, "User aborted launch")
                return
        match self.version_id:
            case "latest-release":
                self.version_id = version_manager.get_latest_release()
            case "latest-snapshot":
                self.version_id = version_manager.get_latest_snapshot()

        self.status.emit("Fetching version info...")
        version_json = version_manager.fetch_version_json(self.version_id)
        version_json = version_manager.resolve_inheritence(version_json)

        self.status.emit("Downloading client JAR...")
        jar_path = version_manager.download_client_jar(
            version_json,
            progress_callback=lambda c, t: self.progress.emit(
                f"{self.version_id}.jar", c / 1_000_000, t / 1_000_000, True
            ),
        )

        # self.status.emit("Checking for assets...")
        # asset_index = asset_manager.filter_assets_downloads(
        #     asset_manager.fetch_asset_index(version_json),
        #     progress_callback=lambda c, t: self.progress.emit(
        #         "Checking assets", c, t
        #     )
        # )
        self.status.emit("Downloading assets...")
        asset_manager.download_assets_threaded(
            asset_manager.fetch_asset_index(version_json),
            progress_callback=lambda c, t: self.progress.emit(
                "Downloading assets", c, t, False
            ),
        )

        self.status.emit("Checking log4j config file...")
        log4j_config = asset_manager.check_or_download_logging_config(
            version_json
        )

        self.status.emit("Downloading libraries...")
        libs = library_manager.filter_libraries(version_json)
        library_manager.download_libraries_threaded(
            libs,
            progress_callback=lambda c, t: self.progress.emit(
                "Downloading libraries", c, t, False
            ),
        )
        library_manager.download_natives(libs)
        natives_dir = MINECRAFT_DIR / "bin" / self.version_id
        natives_dir = library_manager.extract_natives(libs, natives_dir)

        self.status.emit("Checking for Java install...")
        profile_jre = self.profile_data.java_path
        if profile_jre:
            try:
                subprocess.run(
                    [profile_jre.replace("javaw", "java"), "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                self.log.error(
                    "Java exited with code %d:\n%s",
                    err.returncode,
                    str(err.output),
                )
                self.log.info(
                    "Aborting launch, and notifying user of invalid "
                    "JRE location."
                )
                self.finished.emit(False, str(err.output))
                return
            else:
                java_exc = Path(profile_jre)
        else:
            jre_name = version_json.get("javaVersion", {}).get("component", "")
            jre_manifest = java_manager.get_jvm_version_manifest(jre_name)
            if not offline_mode:
                self.status.emit("Downloading Java...")
                java_exc = java_manager.install_java_version_threaded(
                    jre_name,
                    jre_manifest,
                    progress_callback=lambda c, t: self.progress.emit(
                        "Downloading Java", c, t, False
                    ),
                )
            else:
                self.log.warning(
                    "Offline mode active, JRE executable may be broken!"
                )
                try:
                    java_exc = java_manager.find_java_exc(jre_name)
                except RuntimeError as err:
                    self.log.error(
                        "Failed to find JRE installation!", exc_info=err
                    )
                    self.finished.emit(False, str(err))
                    return

        match OS:
            case "windows":
                pass
            case _:
                java_manager.mark_executable(java_exc)

        classpath = library_manager.build_classpath(libs, jar_path)

        if self.auth_info.token_valid:
            reauth = False
        else:
            self.log.warning(
                "User account doesn't have a valid token, "
                "trying to refresh..."
            )
            self.status.emit("Reauthenticating...")
            try:
                self.auth_info.minecraft_auth()
            except RuntimeError as err:
                self.log.error(
                    "Failed to authenticate account, aborting launch.",
                    exc_info=err,
                )
                if getattr(err, "__notes__", None):
                    self.finished.emit(False, str(err.__notes__))
                else:
                    self.finished.emit(False, str(err))
                return
            except requests.RequestException as err:
                self.log.error(
                    "Failed to authenticate account (are we offline?):",
                    exc_info=err,
                )
                self.finished.emit(False, str(err))
                return
            reauth = True
        assert self.auth_info.token
        if self.auth_info.profile:
            reauth = max(reauth, False)
        else:
            log.warning(
                "Account doesn't have associated profile info, trying "
                "to fetch it..."
            )
            try:
                self.auth_info.get_profile_info()
            except Exception as err:
                self.log.error(
                    "Failed to fetch profile info (are we offline?)",
                    exc_info=err,
                )
                self.finished.emit(False, str(err))
                return
            else:
                log.info("Got profile info for '%s'", self.auth_info.gamertag)
                assert self.auth_info.profile
                reauth = True

        if reauth:
            account_manager.save_or_replace_account(self.auth_info)

        self.status.emit("Launching Minecraft...")
        cmd = build_launch_command(
            version_json,
            self.auth_info.profile.name,
            self.auth_info.profile.uuid,
            self.auth_info.token.access_token,
            self.auth_info.player_type,
            self.auth_info.demo_mode,
            self.auth_info.xuid,
            str(java_exc),
            log4j_config,
            classpath,
            self.profile_data.game_dir,
            self.profile_data.jvm_args,
            self.profile_data.memory_min,
            self.profile_data.memory_max,
            self.profile_data.resolution_width,
            self.profile_data.resolution_height,
            self.profile_data.mods_folder,
            self.profile_data.mods_folder_mode,
        )
        logged_cmd = " ".join(cmd).replace(
            self.auth_info.token.access_token, "TOKEN"
        )
        self.log.info("Launch command: '%s'", logged_cmd)

        sub_logger = logging.getLogger(Path(cmd[0]).name)
        self._p = launch_game(cmd, cwd=self.profile_data.game_dir)
        if self._p.poll() is None:
            self.finished.emit(True, "Minecraft launched successfully.")
        else:
            self.log.warning("Game hasn't given a return code, did it launch?")
            self.finished.emit(True, "Unknown status")

        if DEV and config.post_launch_option < 1:
            game_log_func = sub_logger.debug
        else:

            def game_log_func(msg: object, *args): ...

        # reverse this when reading:
        stdout_cache: list[str] = []

        if self.emit_logs and not self._hook:
            self._hook = self.game_log.emit

        if self._hook:

            def loop(self):
                nonlocal stdout_cache
                if self._p.stdout:
                    for line in iter(self._p.stdout.readline, ""):
                        stdout_cache.insert(0, line[:-1])
                        self._hook(line[:-1])

                        self._p.stdout.flush()
                        stdout_cache = stdout_cache[:255]
                self._p.wait()

        else:

            def loop(self):
                nonlocal stdout_cache
                if self._p.stdout:
                    for line in iter(self._p.stdout.readline, ""):
                        game_log_func(line[:-1])  # skip newline
                        stdout_cache.insert(0, line[:-1])

                        # memory usage
                        self._p.stdout.flush()
                        stdout_cache = stdout_cache[:255]  # 256 lines
                self._p.wait()

        loop(self)

        stdout_cache.reverse()
        stdout = "\n".join(stdout_cache)

        self.log.debug("Returned with code %d", self._p.returncode)
        if self._p.returncode == 0:
            if config.redownload_option > 1:
                config.redownload_option = 0
        self.game_closed.emit(str(self._p.returncode), stdout)
