from argparse import ArgumentParser, ArgumentError
from pathlib import Path
import os

_parser = ArgumentParser()

_work_dir = _parser.add_argument("-d", "--workDir", type=Path, dest="work_dir")

_resource_debug = _parser.add_argument(
    "-1", "--resourceDebug", action="store_true", default=False,
    dest="resource_debug"
)

_parsed_args = _parser.parse_args()

if _parsed_args and (isinstance(_parsed_args.work_dir, Path)
    and not _parsed_args.work_dir.exists()):
    try:
        _parsed_args.work_dir.mkdir(parents=True)
    except Exception as err:
        raise ArgumentError(_work_dir, "Invaild path: '%s'"
                            % str(_parsed_args.work_dir)) from err

work_dir:Path|None = _parsed_args.work_dir if _parsed_args else None
resource_debug:bool = _parsed_args.resource_debug if _parsed_args else False