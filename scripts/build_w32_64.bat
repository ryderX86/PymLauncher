@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
rem save the current cwd:
set __LAST_CWD=%CD%

rem Make sure the CWD is at the base of the project:
set __CWD=%~dp0
cd %__CWD%
cd ..

call .\.venv\scripts\activate.bat

if exist .\dist (
    del .\dist /s /q
)

python .\resources\compile.py

rem Full send:
pyside6-deploy -c w32.pysidedeploy.spec

if exist .\dist\Launcher.dist (
    cd .\dist\Launcher.dist
    echo Cleaning up unnecessary files:
    for %%x in (
        qt6datavisualization.dll
        qt6datavisualizationqml.dll
        qt6labswavefrontmesh.dll
        qt6multimedia.dll
        qt6multimediaquick.dll
        qt6pdf.dll
        qt6pdfquick.dll
        qt6quick3dparticleeffects.dll
        qt6quick3dparticles.dll
        qt6quick3dspacialaudio.dll
        qt6quick3dxr.dll
        qt6texttospeech.dll
        qt6virtualkeyboard.dll
        qt6virtualkeyboardqml.dll
        qt6virtualkeyboardsettings.dll
        qt6webchannel.dll
        qt6webchannelquick.dll
        qt6webenginecore.dll
        qt6webenginequick.dll
        qt6webenginequickdelegatesqml.dll
        qt6websockets.dll
        qt6webview.dll
        qt6webviewquick.dll
        qt6quickcontrols2.dll
        qt6quickcontrols2basic.dll
        qt6quickcontrols2basicstyleimpl.dll
        qt6quickcontrols2fluentwinui3styleimpl.dll
        qt6quickcontrols2fusion.dll
        qt6quickcontrols2fusionstyleimpl.dll
        qt6quickcontrols2imagine.dll
        qt6quickcontrols2imaginestyleimpl.dll
        qt6quickcontrols2impl.dll
        qt6quickcontrols2material.dll
        qt6quickcontrols2materialstyleimpl.dll
        qt6quickcontrols2universal.dll
        qt6quickcontrols2universalstyleimpl.dll
        qt6quickcontrols2windowsstyleimpl.dll
        qt6quick3deffects.dll
        qt6quickeffects.dll
        qt6quicktemplates.dll
        qt6quicktest.dll
        qt6quicktests.dll
        qt6sensors.dll
        qt6sensorsqml.dll
        qt6spacialaudio.dll
        qt6sql.dll
        qt6statemachine.dll
        qt6statemachineqml.dll
        qt6test.dll
        qt63danimation.dll
        qt63dcore.dll
        qt63dextras.dll
        qt63dinput.dll
        qt63dlogic.dll
        qt63drender.dll
        .\PySide6\qml\Qt5Compat
        .\PySide6\qml\QtCharts
        .\PySide6\qml\QtDataVisualization
        .\PySide6\qml\QtGraphs
        .\PySide6\qml\QtLocation
        .\PySide6\qml\QtMultimedia
        .\PySide6\qml\QtRemoteObjects
        .\PySide6\qml\QtScxml
        .\PySide6\qml\QtSensors
        .\PySide6\qml\QtTest
        .\PySide6\qml\QtTextToSpeech
        .\PySide6\qml\QtWebChannel
        .\PySide6\qml\QtWebEngine
        .\PySide6\qml\QtWebSockets
        .\PySide6\qml\QtWebView
    ) do (
        if exist %%x (
            echo Deleting %%x
            del %%x /s /q
        ) else (
            echo %%x doesn't exist, continuing
        )
    )
    echo Cleanup done

    cd ..
    cd ..
)

echo PySide6 deploy done, NSIS:
cd .\scripts
makensis /V3 /NOCD w32installer.nsi "/XOutFile ..\dist\installer.exe"

rem restore everything:
cd %__LAST_CWD%
@echo on

:END