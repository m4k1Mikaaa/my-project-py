@echo off
rem Change directory to the script's location to ensure poetry commands work correctly
cd /d %~dp0

rem Change into the source directory before running the module
cd src

rem This command uses Poetry to find the correct virtual environment
rem and run the application's main script within it.
poetry run python -m main
