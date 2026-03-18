@echo off
REM Start Phoebe Dashboard
REM Usage: start.bat [tome_path]
cd /d "%~dp0"
set TOME=%1
if "%TOME%"=="" set TOME=demo.tome
echo Phoebe Dashboard → http://127.0.0.1:8888
echo Tome: %TOME%
set PYTHONPATH=src
.venv\Scripts\python.exe -m phoebe.dashboard.app %TOME%
