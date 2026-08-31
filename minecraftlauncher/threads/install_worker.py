"""
Contains the class used to download the entire game version.
"""

import logging
import os
import subprocess

from PySide6.QtCore import QThread, Signal

from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.back import (
    asset_manager,
    java_manager,
    library_manager,
    version_manager,
)
from minecraftlauncher.datatypes import LaunchProfile
from minecraftlauncher.exceptions.back import (
    MarkExecutableError,
)
from minecraftlauncher.functions import is_path_valid
from minecraftlauncher.paths import paths

log = logging.getLogger(__name__)


class InstallWorker(QThread):
    """Background worker for downloading game files"""

    progress = Signal(
        str, float, float, bool
    )  # step label, current, total, is mb
    done = Signal(bool)  # successful, message
    error = Signal(BaseException)
    status = Signal(str)  # status text

    log = log.getChild("LaunchWorker")

    # instance attributes
    version_id: str
    launch_profile: LaunchProfile
    account: LauncherAccount
    emit_status: bool
    version_json: dict
    java_executable_path: str
    jar_path: str
    log4j_cfg_path: str | None
    libraries: list[dict]
    natives_dir: str

    def __init__(
        self,
        version_id: str,
        launch_profile: LaunchProfile,
        account: LauncherAccount,
        emit_status: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.version_id = version_id
        self.launch_profile = launch_profile
        self.account = account
        self.emit_status = emit_status
        self.error.connect(lambda e: self.done.emit(False))

    def run(self):
        try:
            self.install()
        except Exception as err:
            log.error(
                "Exception in InstallWorker. Aborting install.",
                exc_info=err,
            )
            self.error.emit(err)
            return

    def install(self):
        match self.version_id:
            case "latest-release":
                self.version_id = version_manager.get_latest_release()
            case "latest-snapshot":
                self.version_id = version_manager.get_latest_snapshot()

        # Checks before doing anything
        if self.launch_profile.java_path:
            self.status.emit("Checking Java installation")
            self.java_executable_path = self._check_user_java_install()

        # Basic downloads
        self.status.emit("Fetching version info")
        self.version_json = self._get_version_info()
        self.status.emit("Downloading client JAR")
        self.jar_path = self._download_jar()
        self.status.emit("Downloading assets")
        self._download_assets()
        self.status.emit("Setting up game logging")
        self.log4j_cfg_path = self._patch_log4j()
        self.status.emit("Downloading libraries")
        self.libraries = self._download_libs()
        self.status.emit("Extracting native libraries")
        self.natives_dir = self._extract_natives()
        if not self.launch_profile.java_path:
            # We check the user's provided Java executable earlier on to avoid
            # wasting any time during the install process if we need to abort
            self.status.emit("Getting Java info")
            self.java_executable_path = self._install_java_recommended()
        log.info("Finished installing %r", self.version_id)
        self.done.emit(True)

    def _check_user_java_install(self):
        profile_jre = self.launch_profile.java_path
        if profile_jre and not (
            is_path_valid(profile_jre) or os.path.isfile(profile_jre)
        ):
            log.warning("Bad Java executable path: %r", profile_jre)
            err = FileNotFoundError(
                f"Invalid Java executable path: {profile_jre!r}"
            )
            err.filename = profile_jre
            raise err
        elif profile_jre:
            try:
                subprocess.run(
                    [profile_jre.replace("javaw", "java"), "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                if isinstance(err.output, (bytes, bytearray)):
                    stdout = err.output.decode("utf-8")
                else:
                    stdout = str(err.output)
                if isinstance(err.stderr, (bytes, bytearray)):
                    stderr = err.stderr.decode("utf-8")
                elif isinstance(err.stderr, str):
                    stderr = err.stderr
                else:
                    stderr = ""
                self.log.warning(
                    "Java version check exited with code %d; output:\n%r",
                    err.returncode,
                    stderr or stdout,
                )
                log.info("Aborting install since Java installation is invalid")
                new = RuntimeError(
                    "Couldn't check Java version; exit code %d", err.returncode
                )
                raise new from err
            except FileNotFoundError as err:
                new = FileNotFoundError(
                    f"Invalid Java executable path: {profile_jre!r}"
                )
                new.filename = profile_jre
                raise new from err
            else:
                return profile_jre
        else:
            err = RuntimeError(
                "Function called without user providing a Java installation"
            )
            raise err

    def _install_java_recommended(self):
        jre_name: str | None = self.version_json.get("javaVersion", {}).get(
            "component"
        )
        if not jre_name:
            log.warning("Aborting game install, couldn't get Java version ID")
            err = RuntimeError("Couldn't find Java version ID")
            raise err
        jre_number: str = self.version_json["javaVersion"].get(
            "majorVersion", jre_name.split("-")[-1].capitalize()
        )
        try:  # TODO: find out what exceptions this can raise and handle them
            manifest = java_manager.get_jvm_version_manifest(jre_name)
        except Exception as err:
            log.error(
                "Failed getting manifest for JRE version %r",
                jre_name,
                exc_info=err,
            )
            raise
        try:
            executable = java_manager.download_java_version(
                jre_name,
                manifest,
                progress_callback=lambda c, t: self.progress.emit(
                    f"Downloading Java {jre_number}", c, t, False
                ),
            )
        except MarkExecutableError as err:
            # macOS/Linux only, usually
            log.error("Failed to mark javaw as executable", exc_info=err)
            if isinstance(err.context, OSError):
                # pylint: disable-next=no-member
                file = err.context.filename or err.context.filename2
                txt = f"Failed to mark {file!r} as executable"
            else:
                txt = "Failed to mark Java as an executable file."
            new = RuntimeError(txt)
            raise new from err
        return executable

    def _extract_natives(self):
        natives_dir = os.path.join(paths.game, "bin", self.version_id)
        return library_manager.extract_natives(self.libraries, natives_dir)

    def _download_libs(self) -> list[dict]:
        try:
            dl_list = library_manager.filter_libraries(self.version_json)
        except Exception as err:
            log.error(
                "Failed library downloads, continuing anyways", exc_info=err
            )
            dl_list: list[dict] = self.version_json.get("libraries", [])
            if not isinstance(dl_list, list) or not dl_list:
                log.warning("Can't continue, no downloads")
                new = RuntimeError("Couldn't get library downloads")
                raise new from err
        library_manager.download_libraries(
            dl_list,
            progress_callback=lambda c, t: self.progress.emit(
                "Downloading libraries", c, t, False
            ),
        )
        return dl_list

    def _patch_log4j(self):
        cfg = asset_manager.check_or_download_logging_config(self.version_json)
        return cfg

    def _download_assets(self):
        index = asset_manager.fetch_asset_index(self.version_json)
        asset_manager.download_assets(
            index,
            progress_callback=lambda c, t: self.progress.emit(
                "Downloading assets", c, t, False
            ),
        )
        return

    def _download_jar(self):
        jar_path = version_manager.download_client_jar(
            self.version_json,
            progress_callback=lambda c, t: self.progress.emit(
                f"{self.version_id}.jar",
                c / 1_000_000,
                t / 1_000_000,
                True,
            ),
        )
        return jar_path

    def _get_version_info(self):
        base_version_json = version_manager.fetch_version_json(self.version_id)
        version_json = version_manager.resolve_inheritence(base_version_json)
        return version_json
