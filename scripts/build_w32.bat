@echo off
rem call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
rem save the current cwd:
set __LAST_CWD=%CD%

rem Make sure the CWD is at the base of the project:
set __CWD=%~dp0
cd %__CWD%
cd..

call .\.venv\scripts\activate.bat

if exist .\dist\installer.exe (
    del .\dist\installer.exe /q
)

cd %__CWD%

python -m nbuild %*

cd %__LAST_CWD%