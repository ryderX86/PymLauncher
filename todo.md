# TODO
## Frontend/UI
### Login Window
`minecraftlauncher.front.window.login.__init__`

---
- `QStackedWidget` w/ multiple "pages" for layout
    - (need to adjust size when switching "pages"/ui states)
## Backend
### Account management
`minecraftlauncher.back.account_manager`

`minecraftlauncher.auth.launcher_account.LauncherAccount`

`minecraftlauncher.auth.microsoft_account.MicrosoftAccount`

`minecraftlauncher.auth.xsts_token.XstsToken`


---
- ***DONE!*** ~~Change E-mail-based account selection to XUID-based~~
    - ~~Requires changes in `MicrosoftAccount`, `LauncherAccount`, `XstsToken`,
    and `account_manager`.~~
### Downloads
literally anything to do with downloads/`requests`

---
- Change `requests.X` to `minecraftlauncher.session.X`
    - obviously excluding `requests.exceptions` objects

---
### General
- Implement Packaging package: https://packaging.pypa.io/en/latest/version.html#packaging.version.Version