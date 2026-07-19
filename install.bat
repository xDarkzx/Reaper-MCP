@echo off
setlocal enabledelayedexpansion

echo.
echo  ============================================
echo   ReaperMCP - One-Click Installer
echo   AI-powered music production in REAPER
echo  ============================================
echo.

:: ── Check Python ──────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  Python is not installed or not in PATH.
    echo.
    set /p INSTALL_PY="  Would you like to install Python via winget? (y/n): "
    if /i "!INSTALL_PY!"=="y" (
        echo.
        echo  Installing Python 3.12 via winget...
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        if !errorlevel! neq 0 (
            echo.
            echo  ERROR: winget install failed.
            echo  Download manually from: https://www.python.org/downloads/
            echo.
            pause
            exit /b 1
        )
        echo.
        echo  Python installed! You need to CLOSE and REOPEN this terminal,
        echo  then run install.bat again so Python is in your PATH.
        echo.
        pause
        exit /b 0
    ) else (
        echo.
        echo  ReaperMCP requires Python 3.10+ to run.
        echo  Install it and come back!
        echo.
        echo  Download from: https://www.python.org/downloads/
        echo  IMPORTANT: Check "Add Python to PATH" during installation!
        echo.
        pause
        exit /b 1
    )
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Found Python %PYVER%

:: Verify Python >= 3.10
for /f %%m in ('python -c "import sys; print(sys.version_info.minor)"') do set PY_MINOR=%%m
for /f %%M in ('python -c "import sys; print(sys.version_info.major)"') do set PY_MAJOR=%%M
if !PY_MAJOR! lss 3 (
    echo.
    echo  ERROR: Python 3.10+ is required, but you have Python %PYVER%
    echo  Download from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
if !PY_MAJOR! equ 3 if !PY_MINOR! lss 10 (
    echo.
    echo  ERROR: Python 3.10+ is required, but you have Python %PYVER%
    echo  Download from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ── Install reaper-mcp ──────────────────────────────────────
:: Warn if running inside a virtual environment
if defined VIRTUAL_ENV (
    echo.
    echo  WARNING: You are inside a virtual environment.
    echo  reaper-mcp should be installed globally so Claude Desktop can find it.
    echo  Deactivate your venv first, or run: pip install reaper-mcp outside of it.
    echo.
    pause
    exit /b 1
)

:: Check if pip is available
echo.
echo [2/5] Installing reaper-mcp...
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   pip not found, installing pip...
    python -m ensurepip --upgrade >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo  ERROR: pip is not installed and ensurepip failed.
        echo  Try reinstalling Python with pip enabled.
        echo.
        pause
        exit /b 1
    )
)

:: Install from local directory (not on PyPI yet)
pushd "%~dp0"
python -m pip install -e .
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: pip install failed. Try running as administrator,
    echo  or run manually: python -m pip install -e .
    echo.
    pause
    exit /b 1
)
popd
echo   reaper-mcp installed successfully!

:: ── Set up REAPER auto-start ──────────────────────────────
:: REAPER auto-runs any script literally named __startup.lua found in its
:: Scripts resource folder, on every launch, with no Action-list
:: registration needed. Removes the "load the Lua script every time" step.
echo.
echo [3/5] Setting up REAPER auto-start...

set "REAPER_SCRIPTS_DIR=%APPDATA%\REAPER\Scripts"
set "STARTUP_SCRIPT=%REAPER_SCRIPTS_DIR%\__startup.lua"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if not exist "%REAPER_SCRIPTS_DIR%" (
    echo   REAPER hasn't been run yet ^(no Scripts folder found^) - skipping.
    echo   Run REAPER once, then re-run this installer to enable auto-start,
    echo   or load the script manually ^(see the final instructions below^).
    goto :skip_autostart
)

findstr /c:"reaper_mcp_server.lua" "%STARTUP_SCRIPT%" >nul 2>&1
if !errorlevel! equ 0 (
    echo   Auto-start already configured - skipping.
    goto :skip_autostart
)

if exist "%STARTUP_SCRIPT%" (
    copy "%STARTUP_SCRIPT%" "%STARTUP_SCRIPT%.bak" >nul 2>&1
    (
    echo.
    echo -- Added by the ReaperMCP installer
    echo reaper.defer^(function^(^) reaper.defer^(function^(^) dofile^([[%SCRIPT_DIR%\reaper_scripts\reaper_mcp_server.lua]]^) end^) end^)
    ) >> "%STARTUP_SCRIPT%"
    echo   Found an existing __startup.lua - backed it up to __startup.lua.bak
    echo   and appended ReaperMCP's auto-start to the end of it.
) else (
    (
    echo -- Auto-start ReaperMCP server on REAPER launch.
    echo -- Double-defer ensures REAPER is fully initialized first.
    echo reaper.defer^(function^(^)
    echo   reaper.defer^(function^(^)
    echo     dofile^([[%SCRIPT_DIR%\reaper_scripts\reaper_mcp_server.lua]]^)
    echo   end^)
    echo end^)
    ) > "%STARTUP_SCRIPT%"
    echo   Created: %STARTUP_SCRIPT%
    echo   ReaperMCP will now load automatically every time REAPER starts.
)
:skip_autostart

:: ── Configure Claude Desktop ──────────────────────────────
echo.
echo [4/5] Configuring Claude Desktop...

set "CONFIG_DIR=%APPDATA%\Claude"
set "CONFIG_FILE=%CONFIG_DIR%\claude_desktop_config.json"

set /p CONFIGURE_CLAUDE="  Configure Claude Desktop for ReaperMCP? (y/n): "
if /i not "!CONFIGURE_CLAUDE!"=="y" (
    echo   Skipped. See docs/INSTALLATION.md for manual setup.
    goto :skip_config
)

:: Create directory if it doesn't exist
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

:: Check if config already exists
if exist "%CONFIG_FILE%" (
    :: Check if reaper is already configured
    findstr /c:"\"reaper\"" "%CONFIG_FILE%" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   Claude Desktop config already has reaper entry - skipping.
        goto :skip_config
    )
    :: Back up existing config
    copy "%CONFIG_FILE%" "%CONFIG_FILE%.bak" >nul 2>&1
    echo   Backed up existing config to: %CONFIG_FILE%.bak
    echo.
    echo   Found existing Claude Desktop config at:
    echo   %CONFIG_FILE%
    echo.
    echo   You need to MANUALLY add this inside your "mcpServers" block:
    echo.
    echo     "reaper": {
    echo       "command": "reaper-mcp"
    echo     }
    echo.
    echo   Opening the config file for you...
    notepad "%CONFIG_FILE%"
    goto :skip_config
)

:: No config exists - create fresh one
(
echo {
echo   "mcpServers": {
echo     "reaper": {
echo       "command": "reaper-mcp"
echo     }
echo   }
echo }
) > "%CONFIG_FILE%"
echo   Created Claude Desktop config at:
echo   %CONFIG_FILE%

:skip_config

:: ── Done ──────────────────────────────────────────────────
echo.
echo [5/5] Done!
echo.
echo  ============================================
echo   SETUP COMPLETE!
echo  ============================================
echo.
findstr /c:"reaper_mcp_server.lua" "%STARTUP_SCRIPT%" >nul 2>&1
if !errorlevel! equ 0 (
    echo  Next steps:
    echo.
    echo   1. Open REAPER ^(or restart it if it's already open^) - ReaperMCP
    echo      loads automatically now, nothing to click.
    echo   2. Restart Claude Desktop (if it's open)
    echo   3. Ask Claude: "Get info about the current REAPER project"
    echo.
) else (
    echo  Next steps:
    echo.
    echo   1. Open REAPER
    echo   2. Load the Lua script:
    echo      Actions ^> Show action list ^> Load ReaScript...
    echo      Select: reaper_scripts\reaper_mcp_server.lua
    echo      Click "Run"
    echo   3. Restart Claude Desktop (if it's open)
    echo   4. Ask Claude: "Get info about the current REAPER project"
    echo.
    echo  The Lua script must be running in REAPER for MCP to work.
    echo  You only need to load it once - REAPER remembers it.
    echo.
)
echo  Docs: https://github.com/xDarkzx/Reaper-MCP
echo  ============================================
echo.
pause
