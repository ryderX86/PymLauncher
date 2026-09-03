# PymLauncher
A custom cross-platform Minecraft Launcher written in Python with a focus on
stability & speed whilst also aiming to be compatible with the official
launcher in launch profile storage, while also providing misc. utilities such
as a built-in Fabric installer, customizable launch profile sorting, built-in
skin changing w/ a 3D preview, encrypted account storage (requires *KDE Wallet*
or *GNOME Keyring* on Linux/Unix-based systems), etc.

## Operating System Support
| OS      | Status          | Notes                                           |
|---------|-----------------|-------------------------------------------------|
| Windows | Fully supported |                                                 |
| Linux   | Fully supported | Encryption requires GNOME Keyring or KDE Wallet |
| macOS   | Support planned | Haven't began testing in macOS yet.             |

## Building from source (WIP)
It is *highly* reccommended you use your own Azure Client ID when building the
launcher. You can register one by following the instructions at
https://minecraft.wiki/w/Microsoft_authentication, then adding the following
parameter when building: `--azure-client-id={CLIENT_ID}`, or paste it into a
file at the root directory called `.azure-client-id`

For testing pre-build without having to re-sign in constantly, add the client
ID under the environment variable `AZURE_CLIENT_ID`.
*(See [constants.py](./minecraftlauncher/constants.py#L25))*
### Windows
#### Prerequesites
- Python (3.13 or newer): https://python.org
    - All packages in requirements.txt are required, requirements-dev.txt is
    optional.
- NSIS (if you want the installer build to be successful):
https://nsis.sourceforge.io/Main_Page

#### Instructions
1. Run `git clone https://github.com/ryderX86/minecraftlauncher-py` or download
the ZIP and extract it.

2. Navigate to the project's root folder, and create a virtual environment
using the following command:
```
python -m venv .venv
```
(Note that running the build script in its current state will fail without
creating a virtual environment)
3. Run `pip install -r requirements.txt`
4. (optional, recommended) Ensure Visual Studio with the MSVC package is
installed if using MSVC (NOT VSCode): https://visualstudio.microsoft.com/
5. Add `makensis` from the NSIS install directory (default:
`C:\Program Files (x86)\NSIS`) to PATH
6. Run either `.\scripts\build_w32.bat` or CD into the `scripts` folder and run
`python -m nbuild` (optionally pass `--debug` to see verbose build info)
7. If everything goes well, check for the `dist` folder at the root of the
folder you cloned into. `installer.exe` will be the installer NSIS created, and
`minecraftlauncher.dist` will contain the actual program files.

## Launch arguments
### Launch Profile
```
--launch-profile={profile ID}
```
To launch straight into the game via profile ID, copy the profile ID either by
right clicking on the profile in the profile list or open
`.../.minecraft/launcher_profiles.json` and get the profile ID from there, then
use the following command, replacing `{profile ID}` with your copied profile
ID.
## Developer/debug launch arguments
### Debug logging
```
--debug
```
More verbose logging in console & log files.
### Change launcher data folder
```
launcher --workDir={YOUR DIRECTORY}
```
Aliases: `--work_dir`, `-wd`
### Change .minecraft folder
```
launcher --gameDir={YOUR DIRECTORY}
```
Aliases: `--game_dir`, `-gd`
## License
This project is licensed under the BSD 3-Clause license.

For more information, see LICENSE.md