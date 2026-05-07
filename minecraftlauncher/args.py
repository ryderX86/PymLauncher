from argparse import ArgumentParser, ArgumentError
import os

_parser = ArgumentParser()

_work_dir = _parser.add_argument(
    "-wd",
    "--workDir",
    "--work_dir",
    "--work-dir",
    type=str,
    dest="work_dir",
    default=None,
)
_parser.add_argument(
    "--resourceDebug",
    action="store_true",
    default=False,
    dest="resource_debug",
)
_parser.add_argument(
    "-exp",
    "--debug-exports",
    "--debug-imports",
    "--imp",
    action="store_true",
    default=False,
    dest="exporting_debug",
)
_parser.add_argument(
    "--debug-splash-screen",
    action="store_true",
    default=False,
    dest="debug_splash_screen",
)
_parser.add_argument(
    "--debug", action="store_true", default=False, dest="debug_logging"
)
_parser.add_argument("--launch-profile", type=str, dest="launch_profile")
_parsed_args = _parser.parse_args()

work_dir: str | None = _parsed_args.work_dir if _parsed_args else None
resource_debug: bool = _parsed_args.resource_debug if _parsed_args else False
exporting_debug = _parsed_args.exporting_debug if _parsed_args else False
debug_logging = _parsed_args.debug_logging if _parsed_args else False
launch_profile: str | None = _parsed_args.launch_profile
debug_splash_screen: bool = _parsed_args.debug_splash_screen

if work_dir is not None:
    work_dir = os.path.normpath(work_dir)
    if not os.path.isdir(_parsed_args.work_dir):
        try:
            os.makedirs(_parsed_args.work_dir, exist_ok=True)
        except OSError as err:
            raise ArgumentError(
                _work_dir,
                f"Failed to create path at {_parsed_args.work_dir}",
            ) from err
