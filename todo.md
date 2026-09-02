# TODO
Things that need doing
## User-end QoL changes
- Disable version list refresh button upon going into offline mode
## Dev-end QoL changes
- Subclass `QPushButton` and create a copy-to-clipboard button for easy re-use
## Structural changes
- Split profiles page into the page itself, and two widgets:
    1. Individual profile editor
    2. Profile selector

    Afterward, investigate whether the QSelectionModel should be replaced or
    subclassed.
- Create a class for profile management as in `account_manager.py`
- Create classes for game versions, libraries/natives, JRE versions, etc., and
change the managers for those accordingly.