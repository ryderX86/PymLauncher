[app]

# title of your application
title = Launcher

# project root directory. default = The parent directory of input_file
project_dir = .

# source file entry point path. default = main.py
input_file = minecraftlauncher

# directory where the executable output is generated
exec_directory = .\dist

# application icon
icon = ./resources/_dist/icon.ico

[python]

# python path
python_path = C:\Users\User\Documents\dev\minecraftlauncher-py\.venv\Scripts\python.exe

# python packages to install
packages = Nuitka==4.0.8

# buildozer = for deploying Android application
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files = resources\3d-raw\Alex.qml,resources\3d\alex\Alex.qml,resources\3d\alex\scene.qml,resources\3d\steve\Steve.qml,resources\3d\steve\scene.qml
modules = Core,Gui,Qml,Quick,Quick3D,QuickWidgets,Svg,SvgWidgets,Widgets
excluded_qml_plugins = QtCharts,QtSensors,QtWebEngine,Qt5Compat,QtCharts,QtDataVisualization,QtGraphs,QtLocation,QtMultimedia,Qt3D,QtRemoteObjects,QtScxml,QtSensors,QtTest,QtTextToSpeech,QtWebChannel,QtWebSockets,QtWebView
plugins = qml,accessiblebridge,egldeviceintegrations,generic,iconengines,imageformats,platforminputcontexts,platforms,platforms/darwin,platformthemes,styles,wayland-decoration-client,wayland-graphics-integration-client,wayland-shell-integration,xcbglintegrations

[android]

[nuitka]

# usage description for permissions requested by the app as found in the info.plist file
# of the app bundle. comma separated
macos.permissions = 

# mode of using nuitka. accepts standalone or onefile. default = onefile
mode = standalone

# specify any extra nuitka arguments
# eg = extra_args = --show-modules --follow-stdlib
extra_args = --python-flag=-m --remove-output --windows-console-mode=disable --output-filename=launcher.exe

#  --user-package-configuration-file = ./scripts/w32.nuitka.yaml

[buildozer]

# build mode
# possible values = ["aarch64", "armv7a", "i686", "x86_64"]
# release creates a .aab, while debug creates a .apk
mode = debug

# path to pyside6 and shiboken6 recipe dir
recipe_dir = 

# path to extra qt android .jar files to be loaded by the application
jars_dir = 

# if empty, uses default ndk path downloaded by buildozer
ndk_path = 

# if empty, uses default sdk path downloaded by buildozer
sdk_path = 

# other libraries to be loaded at app startup. comma separated.
local_libs = 

# architecture of deployed platform
arch = 

