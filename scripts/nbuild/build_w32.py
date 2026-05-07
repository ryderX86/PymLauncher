import subprocess
import logging
import sys

from . import (
    CWD,
    VENV_PATH,
    NOINCLUDE_DATA,
    NOINCLUDE_LIBS,
    RESOURCE_COMPILE_SCRIPT,
    ICO_PATH,
    PROJECT_TOML,
    BASE_ARGS,
)

log = logging.getLogger(__name__)

py_exec = VENV_PATH / "Scripts" / "python.exe"

log.debug("Python executable: %s", py_exec)

log.info("Running ./resources/compile.py")
p = subprocess.run(
    [py_exec, RESOURCE_COMPILE_SCRIPT],
    -1,
    check=False,
    cwd=CWD,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=5,
)
compile_py_logger = logging.getLogger("compile.py")


def read_subprocess_info(logger, debug=True):
    if debug:
        func = logger.debug
    else:
        func = logger.info
    for line in p.stdout.splitlines():
        func(line.decode())
    for line in p.stderr.splitlines():
        func(line.decode())


if p.returncode != 0:
    log.error("Failed to run resources script!")
    read_subprocess_info(compile_py_logger, False)
    p.check_returncode()
else:
    log.info("Script finished.")
    read_subprocess_info(compile_py_logger)
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
    '--file-description="Minecraft Launcher written in Python"',
    "--user-package-configuration-file=./scripts/nuitka.yaml",
]

for d in NOINCLUDE_DATA:
    arg = f"--noinclude-data-files={d}"
    args.append(arg)

for d in NOINCLUDE_LIBS:
    arg = f"--noinclude-dlls={d.lower()}.dll"
    args.append(arg)

args.append("minecraftlauncher")

log.info("Running Nuitka")
p = subprocess.run(
    args, stdout=sys.stdout, stderr=sys.stderr, cwd=CWD, check=False
)
if p.returncode != 0:
    log.error("Build unsuccessful. Exiting early.")
    sys.exit(1)

log.info("Nuitka finished, running MakeNSIS")

nsis_args = [
    "makensis",
    "/V3",
    "/NOCD",
    f"/DPROG_NAME={PROJECT_TOML["project"]["name"]}",
    f"/DPROG_VERSION={PROJECT_TOML["project"]["version"]}",
    "w32installer.nsi",
    "/XOutFile ..\\dist\\installer.exe",
]

nsis_cwd = CWD / "scripts"

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
    read_subprocess_info(nsis_logger)

log.info("Build successful.")
