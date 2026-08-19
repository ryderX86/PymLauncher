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


class LaunchArgsContainer:
    ready: bool = False

    work_dir: str | None
    game_dir: str | None
    resource_debug: bool
    exporting_debug: bool
    debug_logging: bool
    launch_profile: str | None
    debug_splash_screen: bool

    def __init__(self):
        self.work_dir = None
        self.game_dir = None
        self.resource_debug = False
        self.exporting_debug = False
        self.debug_logging = False
        self.launch_profile = None
        self.debug_splash_screen = False

    def get_args(self):
        args = _parser.parse_args()

        self.work_dir = args.work_dir
        self.game_dir = args.game_dir
        self.resource_debug = args.resource_debug
        self.exporting_debug = args.exporting_debug
        self.debug_logging = args.debug_logging
        self.launch_profile = args.launch_profile
        self.debug_splash_screen = args.debug_splash_screen

        if self.work_dir is not None:
            self.work_dir = os.path.normpath(self.work_dir)
            if not os.path.isdir(args.work_dir):
                try:
                    os.makedirs(args.work_dir, exist_ok=True)
                except OSError as err:
                    raise ArgumentError(
                        _work_dir,
                        f"Failed to create path at {args.work_dir}",
                    ) from err

        self.ready = True


launchargs = LaunchArgsContainer()
