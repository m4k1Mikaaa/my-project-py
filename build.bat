@echo off
title MiKA Rental - Builder
chcp 65001 > nul

rem --- Parse Arguments ---
set "BUILD_MODE=onefolder"
set "CREATE_INSTALLER=false"

if /I "%1" == "onefile" ( set "BUILD_MODE=onefile" )
if /I "%2" == "onefile" ( set "BUILD_MODE=onefile" )
if /I "%1" == "installer" ( set "CREATE_INSTALLER=true" )
if /I "%2" == "installer" ( set "CREATE_INSTALLER=true" )

echo =================================================
echo  MiKA Rental Builder
echo  Build Mode: %BUILD_MODE%
echo  Create Installer: %CREATE_INSTALLER%
echo =================================================
echo.

rem --- Step 1: Build the application executable ---
echo [STEP 1] Building the application...

rem Change directory to the script's location to ensure poetry commands work correctly
cd /d %~dp0

echo Running PyInstaller...
echo This may take a few minutes.
echo.

poetry run pyinstaller mika_rental.spec --noconfirm --clean

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to build the application. Build process aborted.
    pause
    exit /b 1
)

rem --- Check for build output ---
set "OUTPUT_PATH="
if "%BUILD_MODE%" == "onefolder" (
    if exist "dist\Mika_Rental\Mika_Rental.exe" (
        set "OUTPUT_PATH=dist\Mika_Rental"
        echo.
        echo Application build successful. The application bundle can be found in the '%OUTPUT_PATH%' folder.
    )
) else (
    if exist "dist\Mika_Rental.exe" (
        set "OUTPUT_PATH=dist"
        echo.
        echo Application build successful. The single executable can be found in the '%OUTPUT_PATH%' folder.
    )
)

if not defined OUTPUT_PATH (
    echo ERROR: Build output not found. Build process aborted.
    pause
    exit /b 1
)

rem --- Step 2: Check if installer build is requested ---
if "%CREATE_INSTALLER%" == "false" (
    echo Build complete. To also create an installer, run: build.bat installer
    pause
    exit /b 0
)

echo =================================================
echo  [STEP 2] Creating Installer
echo =================================================
echo.

rem --- Find Inno Setup and compile the installer ---
set "ISCC_PATH="
rem Check default installation paths for Inno Setup
if exist "%ProgramFiles(x86)%\Inno Setup 6\iscc.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\iscc.exe"
if exist "%ProgramFiles%\Inno Setup 6\iscc.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\iscc.exe"

if not defined ISCC_PATH (
    echo.
    echo ERROR: Inno Setup Compiler (iscc.exe) not found.
    echo Please install Inno Setup 6 from jrsoftware.org and ensure it's in the default location.
    pause
    exit /b 1
)

echo Using Inno Setup Compiler at: %ISCC_PATH%
"%ISCC_PATH%" "Mika_Rental_Setup.iss"

echo.
echo =================================================
echo  Installer creation complete!
echo  Find your setup file in the 'Installer_Output' folder.
echo =================================================
pause
