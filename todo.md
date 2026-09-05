# TODO
Things that need doing
## User-end QoL changes
- Disable version list refresh button upon going into offline mode
- Download "<...>.sha1" files for bulk downloads when there's no SHA1 in the
manifest
## Dev-end QoL changes
- Rework `LoginRedirectWebserver` to be more clearly named & more stable.
## Structural changes
- Split profiles page into the page itself, and two widgets:
    1. Individual profile editor
    2. Profile selector

    Afterward, investigate whether the QSelectionModel should be replaced or
    subclassed.
- Create a class for profile management as in `account_manager.py`
- Create classes for game versions, libraries/natives, JRE versions, etc., and
change the managers for those accordingly.
- Rework QSS/QStyles logic for less complexity
- Rework profile exporting/importing & remove feature flag requirement
*(lowest priority)*