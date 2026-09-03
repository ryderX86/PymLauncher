import logging
import os
import subprocess
import sys

from . import (
    BASE_ARGS,
    CWD,
    FLAGS,
    ICO_PATH,
    NOINCLUDE_DATA,
    NOINCLUDE_LIBS,
    PROJECT_TOML,
    RESOURCE_COMPILE_SCRIPT,
    VENV_PATH,
    BuildFlags,
)

log = logging.getLogger(__name__)

py_exec = VENV_PATH / "Scripts" / "python.exe"

log.debug("Python executable: %s", py_exec)


def read_subprocess_info(process, logger, debug=True):
    if debug:
        func = logger.debug
    else:
        func = logger.info
    for line in process.stdout.splitlines():
        func(line.decode())
    for line in process.stderr.splitlines():
        func(line.decode())


if FLAGS & BuildFlags.RESOURCES:
    log.info("Running ./resources/compile.py")
    p = subprocess.run(
        [py_exec, RESOURCE_COMPILE_SCRIPT],
        -1,
        check=False,
        cwd=CWD,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    compile_py_logger = logging.getLogger("compile.py")

    if p.returncode != 0:
        log.error("Failed to run resources script!")
        read_subprocess_info(p, compile_py_logger, False)
        p.check_returncode()
    else:
        log.info("Script finished.")
        read_subprocess_info(p, compile_py_logger)
        del compile_py_logger

args = [
    py_exec,
    "-m",
    "nuitka",
    *BASE_ARGS,
    # attach keeps subprocess.Popen() from working properly, for some reason
    "--windows-console-mode=attach",
    f"--windows-icon-from-ico={ICO_PATH}",
    "--output-filename=launcher.exe",
    f"--product-version={PROJECT_TOML["project"]["version"]}",
    f"--product-name={PROJECT_TOML["project"]["name"]}",
    # this should probably come from pyproject.toml as well?
    "--file-description=Minecraft Launcher (python)",
    "--user-package-configuration-file=./scripts/nuitka.yaml",
]

for d in NOINCLUDE_DATA:
    arg = f"--noinclude-data-files={d}"
    args.append(arg)

for d in NOINCLUDE_LIBS:
    arg = f"--noinclude-dlls={d.lower()}.dll"
    args.append(arg)

args.append("minecraftlauncher")

if FLAGS & BuildFlags.EXECUTABLE:
    log.info("Running Nuitka")
    p = subprocess.run(
        args, stdout=sys.stdout, stderr=sys.stderr, cwd=CWD, check=False
    )
    if p.returncode != 0:
        log.error("Build unsuccessful. Exiting early.")
        sys.exit(1)

log.debug("Checking for NSIS installation")
makensis = None
PATH = os.environ["PATH"].split(";")
for p in PATH:
    file_name = os.path.splitext(os.path.split(p)[-1])[0]
    nsis_dir = os.path.split(p)[-1]
    if file_name.lower() == "makensis":
        makensis = p
        break
    elif nsis_dir.upper() == "NSIS":
        file_name = os.path.join(nsis_dir, "makensis.exe")
        if os.path.isfile(file_name):
            makensis = file_name
            break
if not makensis:
    PROGFILES = os.environ["PROGRAMFILES"]
    PROGFILES86 = os.environ["PROGRAMFILES(X86)"]
    MAKENSIS_PROGFILES_PATH = ("NSIS", "makensis.exe")
    makensis_path_64 = os.path.join(PROGFILES, *MAKENSIS_PROGFILES_PATH)
    makensis_path_32 = os.path.join(PROGFILES86, *MAKENSIS_PROGFILES_PATH)
    if os.path.isfile(makensis_path_32):
        makensis = makensis_path_32
    elif os.path.isfile(makensis_path_64):
        makensis = makensis_path_64
if not makensis:  # we still don't have it at this point, can't run
    log.warning("No NSIS installation found, not building an installer.")
    FLAGS = FLAGS & ~BuildFlags.INSTALLER

nsis_args = [
    makensis,
    "/V3",
    "/NOCD",
    f"/DPROG_NAME={PROJECT_TOML["project"]["name"]}",
    f"/DPROG_VERSION={PROJECT_TOML["project"]["version"]}",
    "w32installer.nsi",
    "/XOutFile ..\\dist\\installer.exe",
]

nsis_cwd = CWD / "scripts"

if FLAGS & BuildFlags.INSTALLER:
    log.info("Running MakeNSIS")
    p = subprocess.run(
        nsis_args,
        cwd=nsis_cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode != 0:
        log.error("Failed to run MakeNSIS!")
        nsis_logger = logging.getLogger("makensis.exe")
        read_subprocess_info(nsis_logger, False)
        log.info("Build unsuccessful.")
        sys.exit(1)
    else:
        nsis_logger = logging.getLogger("makensis.exe")
        read_subprocess_info(p, nsis_logger)

log.info("Build successful.")
