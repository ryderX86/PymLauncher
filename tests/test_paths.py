import pytest

from launcher._paths import PathFinder
from launcher.functions.text import is_path_valid


def test_valueerror():
    pf = PathFinder()
    with pytest.raises(ValueError):
        pf.setup("\\\\\\\\.,;,'''\"\"")
        pf.generate_folder_structure()


def test_traversal_errror():
    assert is_path_valid("..\\..\\..\\test") is False


def test_correctpath():
    pf = PathFinder()
    pf.setup("./data2", "./data2")
