# TODO
Things that need doing
## User-end QoL changes
- [ ] Disable version list refresh button upon going into offline mode
- [ ] Download "<...>.sha1" files for bulk downloads when there's no SHA1 in
      the manifest
- [ ] Rework QML for the skin change window to use one continuous view for both
      skin models, and simply swap visibility instead of needing to refresh the
      entire view.
## Dev-end QoL changes
- [ ] Rework `LoginRedirectWebserver` to be more clearly named & more stable.
- [ ] Move web request logic from `launcher.front.skin_change` to a
module/class in `launcher.auth` (probably `MinecraftProfile`)
- [ ] Rework `LaunchProfile` and move away from using dataclasses for it
- [ ] De-tangle the bootstrap process in `launcher.__main__`.
- [ ] Create classes for and rework QML for the skin change window to use said
      classes. (See: https://doc.qt.io/qtforpython-6/PySide6/QtQml/QmlElement)
## Structural changes
- [x] Split profiles page into the page itself, and two widgets:
    1. Individual profile editor
    2. Profile selector

    Afterward, investigate whether the QSelectionModel should be replaced or
    subclassed.
   **(COMPLETED)**
- [ ] Create a class for profile management as in `account_manager.py`
- [x] Create classes for game versions, libraries/natives, JRE versions, etc.,
      and change the managers for those accordingly.
- [ ] Rework QSS/QStyles logic for less complexity (in progress)
- [ ] Rework profile exporting/importing & remove feature flag requirement
      *(lowest priority)*