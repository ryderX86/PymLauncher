@echo off
rem save the current cwd:
set __LAST_CWD=%CD%

rem Make sure the CWD is at the base of the project:
set __CWD=%~dp0
cd %__CWD%
cd ..

call .\.venv\scripts\activate.bat

if exist .\dist (
    del .\dist /Q
)

python .\resources\compile.py

rem Full send:
pyside6-deploy -c .\scripts\w32.pysidedeploy.spec -f

echo PySide6 deploy done, NSIS:
cd .\scripts
makensis /V3 /NOCD w32installer.nsi "/XOutFile ..\dist\installer.exe"

rem restore everything:
cd %__LAST_CWD%
@echo on

:END