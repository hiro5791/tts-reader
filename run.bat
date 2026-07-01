@echo off
REM Multi Voice Studio launcher - always use .venv-build so Irodori runs in-process.
REM (ASCII only on purpose: cmd.exe reads .bat in the system codepage, so non-ASCII breaks it.)
cd /d "%~dp0"
set "HF_HOME=%~dp0models"
set "VIRTUAL_ENV="
".venv-build\Scripts\python.exe" app.py
if errorlevel 1 pause
