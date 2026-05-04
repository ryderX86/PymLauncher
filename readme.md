# ryderX86/Minecraft Launcher
Minecraft Launcher written in Python with a focus on stability & speed whilst
also aiming to be compatible with the official launcher for profile storage.

## Building from source (WIP)
0. Make sure Python is installed (3.11 or later, preferably at least 3.13;
CPython and Anaconda Python are both supported, absolutely not from the Windows
Store or `pyenv` on macOS)

1. Run `git clone https://github.com/ryderX86/minecraftlauncher-py` or download
the ZIP and extract it.

2. Navigate to the project's root folder, and create a virtual environment
using the following command:
```
python -m venv .venv
```
3. Run `pip install -r requirements.txt`
### Windows
4. Ensure NSIS is installed: https://nsis.sourceforge.io/Download
5. Add `makensis` from the NSIS install directory (default:
`C:\Program Files (x86)\NSIS`) to PATH
6. Run either `.\scripts\build_w32.bat` or CD into the `scripts` folder and run
`python -m nbuild` (optionally pass `--debug` to see verbose build info)
7. If everything goes well, check for the `dist` folder at the root of the
folder you cloned into. `installer.exe` will be the installer NSIS created, and
`minecraftlauncher.dist` will contain the actual program files.
### Linux
4. Ensure either GCC (5.1 or higher), Clang, or Zig are installed
4. 

## Launch arguments
### Launch Profile
```
launcher --launch-profile={profile ID}
```
To launch straight into the game via profile ID, copy the profile ID either by
right clicking on the profile in the profile list or open
`.../.minecraft/launcher_profiles.json` and get the profile ID from there, then
use the following command, replacing `{profile ID}` with your copied profile
ID.
## Developer/debug launch arguments
### Debug splash screen
```
launcher --debug-splash-screen
```
Pauses on the splash screen for 5 seconds. Useful for developers only.
### Debug logging
```
launcher --debug
```
More verbose logging saved to file.

`--resource-debug` for logging resource caching functions.

`--debug-exports` `--debug-imports` `--exp` `--imp` for profile
export/importing debug logging.
### Change .minecraft folder
```
launcher --workDir={YOUR DIRECTORY}
```
Aliases: `--work_dir`, `-wd`