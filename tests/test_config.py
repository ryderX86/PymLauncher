from collections.abc import Callable

from launcher import constants
from launcher.config import (
    ConfigHolder,
    JarRedownloadBehavior,
    PostLaunchBehavior,
)


def test_config():
    config = ConfigHolder()

    # these values should all be basically anything EXCEPT what's default
    config.window_size = [2, 4]
    config.use_device_code_for_logins = True
    config.copy_code_for_login = False
    config.post_launch_option = PostLaunchBehavior.KEEP_OPEN
    config.redownload_option = JarRedownloadBehavior.NEVER
    config.maximized = True
    config.tooltip_icons_enabled = False
    config.ignored_messages = {0}
    config.jump_list_items = ["test-profile"]
    config.dialog_answers = {"test": True}
    config.show_animation_on_skin_dialog = True
    config.show_logs_on_home = True
    config.allow_audio = False
    config.enforce_json_spec = True
    config.show_snapshots = False
    config.show_old_releases = False
    config.use_webview_for_login = not constants.FLAG_ENABLE_WEBVIEW

    config.save()

    # set a new config object and have it load to compare the values
    saved_config = ConfigHolder()
    saved_config.load()

    for key, value in saved_config.__dict__.items():
        if key.startswith("_"):
            continue
        elif isinstance(value, Callable):
            continue
        print(
            "testing key %r: original value: %r; saved value: %r",
            key,
            getattr(saved_config, key),
            getattr(config, key),
        )
        assert getattr(saved_config, key) == getattr(config, key)
