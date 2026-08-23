import pytest

from minecraftlauncher.paths import PathFinder


def test_valueerror():
    pf = PathFinder()
    with pytest.raises(ValueError):
        pf.setup("\\\\\\\\.,;,'''\"\"")
        pf.generate_folder_structure()


def test_correctpath():
    pf = PathFinder()
    pf.setup("./data2", "./data2")
