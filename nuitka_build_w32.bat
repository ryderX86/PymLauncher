@echo off
rem save the current cwd:
set __LAST_CWD=%CD%

rem Make sure the CWD is at the base of the project:
set __CWD=%~dp0
cd %__CWD%
cd ..

call .\.venv\scripts\activate.bat

rem Full send:
pyside6-deploy -c w32.pysidedeploy.spec -f

rem restore everything:
cd %__LAST_CWD%
@echo on