"""
Contains the class used to download the entire game version.
"""

import subprocess
import logging
import os

from PySide6.QtCore import QThread, Signal

from minecraftlauncher.functions import is_path_valid
from minecraftlauncher.datatypes import LaunchProfile
from minecraftlauncher.auth import LauncherAccount
from minecraftlauncher.paths import paths
from minecraftlauncher.exceptions.back import (
    MarkExecutableError,
)
from minecraftlauncher.back import (
    version_manager,
    asset_manager,
    library_manager,
    java_manager,
)

log = logging.getLogger(__name__)


class InstallWorker(QThread):
    """Background worker for downloading game files"""

    progress = Signal(
        str, float, float, bool
    )  # step label, current, total, is mb
    done = Signal(bool, str)  # successful, message
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

    def run(self):
        match self.version_id:
            case "latest-release":
                self.version_id = version_manager.get_latest_release()
            case "latest-snapshot":
                self.version_id = version_manager.get_latest_snapshot()

        # Checks before doing anything
        if self.launch_profile.java_path:
            self.status.emit("Checking Java installation")
            if not is_path_valid(self.launch_profile.java_path):
                log.warning(
                    "Aborting install since the user's Java path is invalid "
                    "(path: %r)",
                    self.launch_profile.java_path,
                )
                self.done.emit(
                    False,
                    f"Invalid file path: {self.launch_profile.java_path!r}",
                )
                return
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
            self.status.emit("Installing Java")
            self.java_executable_path = self._install_java_recommended()
        log.info("Finished installing %r", self.version_id)
        self.done.emit(True, "Successful download")

    def _check_user_java_install(self):
        profile_jre = self.launch_profile.java_path
        if profile_jre and not os.path.isfile(profile_jre):
            log.warning("Bad java executable: %r", profile_jre)
            self.done.emit(False, "Couldn't find user-provided Java executable")
            raise RuntimeError(f"Invalid Java executable path: {profile_jre!r}")
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
                    std = err.output.decode("utf-8")
                else:
                    std = str(err.output)
                self.log.warning(
                    "Java version check exited with code %d; output:\n%r",
                    err.returncode,
                    std,
                )
                log.info("Aborting install since Java installation is invalid")
                self.done.emit(False, f"Bad executable path: {profile_jre!r}")
                raise
            else:
                return profile_jre
        else:
            raise RuntimeError(
                "Function called without user providing a Java installation"
            )

    def _install_java_recommended(self):
        jre_name: str | None = self.version_json.get("javaVersion", {}).get(
            "component"
        )
        if not jre_name:
            log.warning("Aborting game install, couldn't get Java version ID")
            self.done.emit(False, "Couldn't get Java version ID")
            raise RuntimeError("Couldn't find Java version ID")
        try:
            manifest = java_manager.get_jvm_version_manifest(jre_name)
        except Exception as err:
            log.error(
                "Failed getting manifest for JRE version %r",
                jre_name,
                exc_info=err,
            )
            self.done.emit(
                False, f"Couldn't get info for JRE version {jre_name!r}"
            )
            raise
        try:
            executable = java_manager.download_java_version(
                jre_name,
                manifest,
                progress_callback=lambda c, t: self.progress.emit(
                    f"Downloading Java {jre_name}", c, t, False
                ),
            )
        except MarkExecutableError as err:
            # macOS/Linux only, usually
            log.error("Failed to mark javaw as executable", exc_info=err)
            if isinstance(err.context, PermissionError):
                # pylint: disable-next=no-member
                file = err.context.filename or err.context.filename2
                self.done.emit(
                    False,
                    f"Failed to mark {file!r} as executable. "
                    "Please ensure you have appropriate permissions.",
                )
            else:
                self.done.emit(
                    False,
                    "An unknown issue occured trying to mark a file as executable. "
                    f"({type(err.context).__name__})",
                )
            raise
        except Exception as err:
            log.error("Failed to download Java %s", jre_name, exc_info=err)
            self.done.emit(False, f"Couldn't download Java {jre_name}")
            raise
        return executable

    def _extract_natives(self):
        natives_dir = os.path.join(paths.game, "bin", self.version_id)

        try:
            return library_manager.extract_natives(self.libraries, natives_dir)
        except Exception as err:
            log.error("Failed extracitng natives", exc_info=err)
            self.done.emit(False, "Failed extracting natives")
            raise

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
                self.done.emit(False, "Couldn't get library downloads")
                raise RuntimeError("Couldn't get library downloads") from err
        try:
            library_manager.download_libraries(
                dl_list,
                progress_callback=lambda c, t: self.progress.emit(
                    "Downloading libraries", c, t, False
                ),
            )
        except Exception as err:
            log.error("Failed to download libraries", exc_info=err)
            self.done.emit(
                False, f"Failed to download libraries ({type(err).__name__})"
            )
            raise
        return dl_list

    def _patch_log4j(self):
        try:
            cfg = asset_manager.check_or_download_logging_config(
                self.version_json
            )
        except Exception as err:
            log.error("Failed to patch Log4J config", exc_info=err)
            self.done.emit(False, "Failed patching logging config")
            raise
        return cfg

    def _download_assets(self):
        try:
            index = asset_manager.fetch_asset_index(self.version_json)
        except Exception as err:
            log.error(
                "Failed to get assets index for %r",
                self.version_id,
                exc_info=err,
            )
            self.done.emit(
                False,
                f"Failed to get assets index " f"({type(err).__name__})",
            )
            raise
        try:
            asset_manager.download_assets(
                index,
                progress_callback=lambda c, t: self.progress.emit(
                    "Downloading assets", c, t, False
                ),
            )
        except Exception as err:
            log.error(
                "Failed to download assets for %r",
                self.version_id,
                exc_info=err,
            )
            self.done.emit(
                False,
                f"Failed to download assets " f"({type(err).__name__})",
            )
            raise
        return

    def _download_jar(self):
        try:
            jar_path = version_manager.download_client_jar(
                self.version_json,
                progress_callback=lambda c, t: self.progress.emit(
                    f"{self.version_id}.jar", c / 1_000_000, t / 1_000_000, True
                ),
            )
        except Exception as err:
            log.error(
                "Failed to download '%s.jar'", self.version_id, exc_info=err
            )
            self.done.emit(
                False,
                f"Failed to download '{self.version_id}.jar' "
                f"({type(err).__name__})",
            )
            raise
        return jar_path

    def _get_version_info(self):
        try:
            base_version_json = version_manager.fetch_version_json(
                self.version_id
            )
        except Exception as err:
            log.error(
                "Failed getting version info for %r:",
                self.version_id,
                exc_info=err,
            )
            self.done.emit(
                False,
                f"Failed to get version info for {self.version_id!r}: "
                f"({type(err).__name__})",
            )
            raise
        try:
            version_json = version_manager.resolve_inheritence(
                base_version_json
            )
        except Exception as err:
            log.error(
                "Inheritence parsing failed for %r:",
                self.version_id,
                exc_info=err,
            )
            self.done.emit(
                False,
                f"Failed parsing inheritence for {self.version_id!r} "
                f"({type(err).__name__})",
            )
            raise
        return version_json
