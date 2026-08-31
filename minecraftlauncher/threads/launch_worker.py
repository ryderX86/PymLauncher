"""
minecraftlauncher.back.game_launcher

Builds the launch command for Minecraft, performs argument-template
substitution, and starts the game process.
"""

from collections.abc import Callable
from string import Template
import logging
import os
import random
import re
import subprocess

from PySide6.QtCore import QThread, Signal

from minecraftlauncher import constants
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.back import java_manager, library_manager
from minecraftlauncher.config import JarRedownloadBehavior, config
from minecraftlauncher.datatypes import LaunchProfile
from minecraftlauncher.functions import is_path_valid
from minecraftlauncher.paths import paths

from .install_worker import InstallWorker

log = logging.getLogger(__name__)

TEMPLATE_LEFTOVERS_REGEX = re.compile(r"${([a-zA-Z0-9_\-]+)}")

MAXIMUM_LOG_LINES = 1024
MAXIMUM_LINE_LENGTH = 65536

LEGACY_LAUNCH_ARGS_DEFAULT = (
    "--username ${auth_player_name} --session ${auth_session} "
    "--versionName ${version_name} "
    "--accessToken ${auth_access_token} --gameDir ${game_directory} "
    "--assetsDir ${assets_root} --userProperties {} "
    "--userType msa"
)


def _substitute(template: str, values: dict[str, str]):
    values = {k: v for k, v in values.items() if v is not None}
    t = Template(template)
    subbed = t.safe_substitute(values)
    # unfrozen only so auth tokens don't get leaked into logs when built:
    if constants.DEV and "${" in subbed:
        leftovers: list[str] = TEMPLATE_LEFTOVERS_REGEX.findall(subbed)
        if "xuid" in leftovers:
            leftovers.remove("xuid")
        if leftovers:
            log.warning(
                "Unsubstituted template leftover(s) in string: '%s'",
                str(leftovers),
            )
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
        if not library_manager.evaluate_rules(rules):
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
        "minecraftArguments", LEGACY_LAUNCH_ARGS_DEFAULT
    )
    if "minecraftArguments" not in version_json:
        log.debug(
            "Using default launch args for legacy game versions. "
            "(minecraftArguments is empty)"
        )

    game_args = _substitute(raw_game_args, values).split()

    jar_path = os.path.join(
        paths.game,
        "versions",
        version_json["id"],
        f"{version_json['id']}.jar",
    )

    default_jvm_args = [
        f"-Djava.library.path={values["natives_directory"]}",
        f"-Dminecraft.launcher.brand={constants.LAUNCHER_NAME}",
        f"-Dminecraft.launcher.version={constants.LAUNCHER_VERSION}",
        f"-Dminecraft.client.jar={jar_path}",
        "-cp",
        values["classpath"],
    ]

    return default_jvm_args, game_args


def build_launch_command(
    version_json: dict,
    account: LauncherAccount,
    java_path: str,
    log4j_config: str | None,
    classpath: str,
    profile: LaunchProfile,
    **kwargs,
):
    """
    Builds the full command to launch the game.

    Returns a list suitable for `subprocess.Popen`.
    """
    version_id: str = version_json.get("id", "")
    if not version_id:
        raise ValueError("Version info missing expected value for 'id'")

    if not java_path:
        java_info = version_json.get("javaVersion", {})
        needed_java_version = java_info.get("component", "")
        java_path = str(java_manager.find_java_exc(needed_java_version))

    jar_path = os.path.join(
        paths.game, "versions", version_id, f"{version_id}.jar"
    )

    asset_index_id: str | None = version_json.get("assetIndex", {}).get("id")
    if not asset_index_id:
        asset_index_id = version_json.get("assets")
    if not asset_index_id:
        raise ValueError(
            "Version info missing expected value for 'assets'"
            " or 'assetsIndex'"
        )

    if profile.game_dir:
        if not os.path.isdir(profile.game_dir):
            if not is_path_valid(profile.game_dir):
                raise ValueError(
                    f"Invalid game directory: {profile.game_dir!r}"
                )
            try:
                os.makedirs(profile.game_dir, exist_ok=True)
            except PermissionError as err:
                raise RuntimeError(
                    f"Couldn't create directory at {profile.game_dir!r} "
                    "due to lack of permissions "
                    f"(code: {err.strerror or err.errno})"
                ) from err
            except Exception as err:
                raise ValueError(
                    f"Couldn't create directory at {profile.game_dir!r} "
                    f"(original exception: {type(err).__name__})"
                ) from err
        game_dir = profile.game_dir
    else:
        game_dir = paths.game

    natives_dir: str = kwargs.get("natives_dir") or os.path.join(
        paths.game, "bin", version_id
    )
    if not os.path.isdir(natives_dir):
        os.makedirs(natives_dir, exist_ok=True)

    if not classpath:
        lib_list = library_manager.filter_libraries(version_json)
        classpath = library_manager.build_classpath(lib_list, jar_path)

    if profile.resolution_height or profile.resolution_width:
        resolution_width = profile.resolution_width or 1024
        resolution_height = profile.resolution_height or 768
    else:
        resolution_width = None
        resolution_height = None

    if not account.token or not account.token_valid:
        raise ValueError(
            f"Account provided (gt {account.gamertag}) either "
            "has no token or an invalid token"
        )
    elif not account.profile:
        raise ValueError(
            f"Account provided (gt {account.gamertag}) has no profile"
        )

    session = f"token:{account.token.access_token}:{account.token.uuid}"

    values = {
        "auth_player_name": account.profile.name,
        "auth_uuid": account.token.uuid,
        "version_name": version_id,
        "version_type": version_json.get("type", "unknown"),
        "auth_access_token": account.token.access_token,
        "auth_session": session,
        "user_properties": "{}",
        "user_type": account.player_type,
        "assets_index_name": asset_index_id,
        "game_assets": os.path.join(paths.game, "assets", "virtual", "legacy"),
        "assets_root": os.path.join(paths.game, "assets"),
        "game_directory": game_dir,
        "clientid": str(random.randint(0, 0xFFFFFF)),
        "auth_xuid": account.xuid,
        "resolution_width": resolution_width,
        "resolution_height": resolution_height,
        "natives_directory": natives_dir,
        "classpath": classpath,
        "library_directory": os.path.join(paths.game, "libraries"),
        "launcher_name": constants.LAUNCHER_NAME,
        "launcher_version": constants.LAUNCHER_VERSION,
        "jar_path": jar_path,
        **kwargs,
    }

    features: list[str] = []
    if resolution_height or resolution_width:
        features.append("has_custom_resolution")
    if account.demo_mode:
        features.append("is_demo_user")

    if "arguments" in version_json.keys():
        jvm_args, game_args = _build_args(version_json, values, features)
    else:
        jvm_args, game_args = _build_legacy_args(
            version_json, values, features
        )

    if profile.mods_folder:
        mods_folder = profile.mods_folder.strip()
        if " " in mods_folder:
            if mods_folder[0] != '"' or mods_folder[-1] != '"':
                mods_folder = f'"{mods_folder}"'
        mods_folder_mode = profile.mods_folder_mode or "modsFolder"
        jvm_args.insert(-2, f"-Dfabric.{mods_folder_mode}={mods_folder}")

    cmd: list[str] = [java_path]

    if constants.OS == "windows":
        cmd.extend(["-Dos.name=Windows 10", "-Dos.version=10.0"])

    cmd.extend(jvm_args)
    if log4j_config:
        cmd.append(log4j_config)

    main_class = version_json.get(
        "mainClass", "net.minecraft.client.main.Main"
    )
    cmd.extend([f"-Xms{profile.memory_min}", f"-Xmx{profile.memory_max}"])
    if profile.jvm_args:
        cmd.extend(profile.jvm_args.split(" "))
    cmd.append(main_class)
    cmd.extend(game_args)

    if resolution_width and resolution_height and "--width" not in cmd:
        cmd.extend(["--width", str(resolution_width)])
    if resolution_width and resolution_height and "--height" not in cmd:
        cmd.extend(["--height", str(resolution_height)])

    return cmd


class LaunchWorker(QThread):
    """Background worker for launching the game."""

    progress = Signal(
        str, float, float, bool
    )  # step label, current, total, is mb
    done = Signal(bool, str)  # successful, message
    status = Signal(str)  # status text
    game_closed = Signal(str, str)
    game_log = Signal(str)
    """
    `[0]` (`int`) - Exit code<br>
    `[1]` (`str`) - stdout<br>
    `[2]` (`str`) - stderr
    """

    log = log.getChild("LaunchWorker")

    # instance attributes
    _ready_for_launch: bool
    installer: InstallWorker
    cwd: str | os.PathLike
    cmd: list[str]
    _p: subprocess.Popen[str] | None
    _callback: Callable[[str], None] | None

    def __init__(
        self,
        installer: InstallWorker,
        log_hook: Callable[[str], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ready_for_launch = False
        self._callback = log_hook
        self.installer = installer
        self._p = None

    def startup_process(self):
        if not self._ready_for_launch:
            raise RuntimeError(
                "startup_process() called on LaunchWorker before "
                "_ready_to_launch is True"
            )
        log.info("Launching Minecraft...")

        kwargs: dict = {}

        if constants.OS == "windows":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 1
            kwargs["startupinfo"] = si

        self._p = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True,
            bufsize=1,
            **kwargs,
        )

        log.info("Minecraft started; PID: %d", self._p.pid)
        return

    def post_launch_loop(self):
        """
        Establishes the logging loop and waiting after the game launches.
        """
        assert self._p is not None

        if self._p.poll() is None:
            self.done.emit(True, "Minecraft launched successfully.")
        else:
            if not self._p.returncode:
                self.log.warning(
                    "Game hasn't given a return code, did it launch?"
                )
                self.done.emit(True, "Unknown status")
            else:
                self.done.emit(
                    False, "Unknown error (return %d)", self._p.returncode
                )

        # reverse this when reading:
        stdout_cache: list[str] = []

        if config.show_logs_on_home and not self._callback:
            self._callback = self.game_log.emit
        elif not self._callback:

            def callback(*args): ...

            self._callback = callback

        line_count = MAXIMUM_LOG_LINES - 1
        line_length = MAXIMUM_LINE_LENGTH - 1

        def loop(self):
            nonlocal stdout_cache
            if self._p.stdout:
                for line in iter(self._p.stdout.readline, ""):
                    trimmed_line = line[:line_length]
                    stdout_cache.insert(0, trimmed_line)
                    self._callback(trimmed_line)

                    self._p.stdout.flush()
                    stdout_cache = stdout_cache[:line_count]
            self._p.wait()

        loop(self)

        stdout_cache.reverse()
        stdout = "".join(stdout_cache)

        self.log.info("Game process returned with code %d", self._p.returncode)
        if self._p.returncode == 0:
            if config.redownload_option > 1:
                config.redownload_option = JarRedownloadBehavior.NEVER
        self.game_closed.emit(str(self._p.returncode), stdout)

    def run(self):
        """
        Main process. Cannot be run before the installer (self.installer) is
        finished (a check is in `start()` for this.)
        """
        self.version_json = self.installer.version_json
        self.launch_profile = self.installer.launch_profile
        self.account = self.installer.account
        self.java_executable_path = self.installer.java_executable_path
        self.jar_path = self.installer.jar_path
        self.log4j_cfg_path = self.installer.log4j_cfg_path
        self.libraries = self.installer.libraries
        self.natives_dir = self.installer.natives_dir

        # this is probably the one thing that can't catastrophically fail
        classpath = library_manager.build_classpath(
            self.libraries, self.jar_path
        )

        # DO NOT add reauthentication logic here. we do this in LauncherApp
        # before even the thought of running this is conjured.

        # assert statements to shut the type checker up
        assert self.account.profile
        assert self.account.token

        self.status.emit("Launching Minecraft...")
        self.cmd = build_launch_command(
            self.version_json,
            self.account,
            self.java_executable_path,
            self.log4j_cfg_path,
            classpath,
            self.launch_profile,
            natives_dir=self.natives_dir,
        )
        logged_cmd = " ".join(self.cmd).replace(
            self.account.token.access_token, "[REDACTED]"
        )
        if constants.OS == "windows":
            logged_cmd.replace("", "")
        self.log.info("Launch command: '%s'", logged_cmd)

        # store the CWD for debugging crashes:
        if self.launch_profile.game_dir:
            self.cwd = self.launch_profile.game_dir
        else:
            self.cwd = paths.game

        self._ready_for_launch = True

        self.startup_process()
        self.post_launch_loop()
        return

    def start_if_success(self, success: bool):
        if success:
            self.start()
        else:
            return

    def _get_hspid_log(self):
        if not self._p:
            log.warning(
                "_get_hspid_log() called too early! "
                "No Popen() instance present."
            )
            return
        pid = self._p.pid
        game_dir: str = self.launch_profile.game_dir or paths.game
        pattern = f"hs_err_pid{pid}.log"
        hserr_log_paths = (
            os.path.join(game_dir, pattern),
            os.path.join(constants.JVM_TEMP_DIR, pattern),
            # only if the argument is supplied (remove if that doesn't get
            # implemented):
            os.path.join(game_dir, "crash-reports", pattern),
        )
        log_file: str | None = None
        for path in hserr_log_paths:
            if os.path.isfile(path):
                # compare timestamp, we want the newest one:
                if log_file is not None:
                    existing_lstat = os.lstat(log_file)
                    new_lstat = os.lstat(path)
                    if existing_lstat.st_mtime > new_lstat.st_mtime:
                        continue
                log_file = path

        if not log_file:
            log.warning(
                "Couldn't get JVM crash log! Locations checked:\n%s",
                "\n".join(f'"  {x}"' for x in hserr_log_paths),
            )

        return log_file

    def start(
        self, /, priority: QThread.Priority = QThread.Priority.NormalPriority
    ) -> None:
        """
        Simple override to add a check that the installer passed at init() is
        done before launching
        """
        if not self.installer.isFinished():
            raise RuntimeError("InstallWorker hasn't finished yet!")
        return super().start(priority)
