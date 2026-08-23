import os

from minecraftlauncher.paths import paths

BASE_DIR = os.path.dirname(__file__)
paths.setup(
    os.path.join(BASE_DIR, "data", "game"),
    os.path.join(BASE_DIR, "data", "launcher"),
)
paths.generate_folder_structure()
