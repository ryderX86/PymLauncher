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
_work_dir = _parser.add_argument(
    "-gd",
    "--gameDir",
    "--game_dir",
    "--game-dir",
    type=str,
    dest="game_dir",
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
    "--debug",
    action="store_true",
    default=False,
    dest="debug_logging",
)
# _parser.add_argument(
#     "--force-offline",
#     "--offline",
#     action="store_true",
#     dest="force_offline",
#     default=False,
# )
_parser.add_argument(
    "--launch-profile",
    type=str,
    dest="launch_profile",
)

# defaults
work_dir: str | None = None
game_dir: str | None = None
resource_debug: bool = False
exporting_debug = False
debug_logging: bool = False
launch_profile: str | None = None
debug_splash_screen: bool = False

ready: bool = False


def get_args():
    global work_dir, resource_debug, exporting_debug, debug_logging
    global launch_profile, debug_splash_screen, game_dir
    _parsed_args = _parser.parse_args()

    work_dir = _parsed_args.work_dir
    game_dir = _parsed_args.game_dir
    resource_debug = _parsed_args.resource_debug
    exporting_debug = _parsed_args.exporting_debug
    debug_logging = _parsed_args.debug_logging
    launch_profile = _parsed_args.launch_profile
    debug_splash_screen = _parsed_args.debug_splash_screen
    # force_offline: bool = _parsed_args.force_offline

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

    global ready
    ready = True

    return {
        "work_dir": work_dir,
        "game_dir": game_dir,
        "resource_debug": resource_debug,
        "exporting_debug": exporting_debug,
        "debug_logging": debug_logging,
        "launch_profile": launch_profile,
        "debug_splash_screen": debug_splash_screen,
    }
