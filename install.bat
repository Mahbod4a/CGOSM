@echo off
REM ═══════════════════════════════════════════════════════════════
REM AIS Global Tracker v15.0 - Windows Installer
REM ═══════════════════════════════════════════════════════════════
setlocal EnableDelayedExpansion

echo.
echo ================================================================
echo      AIS GLOBAL TRACKER v15.0 - Windows Installer
echo           Powered by Cyber Ghost
echo ================================================================
echo.

REM ─── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo         Download from: https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python %PYVER% found
echo.

REM ─── Virtual Environment ──────────────────────────────────────
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
echo [OK] venv activated
echo.

REM ─── Upgrade pip ──────────────────────────────────────────────
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip wheel setuptools --quiet

REM ─── Install Requirements ─────────────────────────────────────
if "%1"=="--minimal" (
    echo [INFO] Installing minimal requirements...
    pip install -r requirements-minimal.txt
) else (
    echo [INFO] Installing full requirements...
    pip install -r requirements.txt
)

if errorlevel 1 (
    echo [ERROR] pip install failed
    pause
    exit /b 1
)

echo [OK] All packages installed
echo.

REM ─── Create Data Directory ────────────────────────────────────
if not exist "AIS_Data" mkdir AIS_Data
echo [OK] AIS_Data\ created
echo.

REM ─── Firewall Rule ────────────────────────────────────────────
echo [INFO] Opening firewall port 7999...
netsh advfirewall firewall add rule name="AIS Tracker 7999" dir=in action=allow protocol=TCP localport=7999 >nul 2>&1
if errorlevel 1 (
    echo [WARN] Could not add firewall rule automatically.
    echo        Run this manually as Administrator:
    echo        netsh advfirewall firewall add rule name="AIS Tracker 7999" dir=in action=allow protocol=TCP localport=7999
) else (
    echo [OK] Firewall rule added
)

echo.
echo ================================================================
echo   Installation complete!
echo ================================================================
echo.
echo   Run:  venv\Scripts\activate ^&^& python CGOSM.py
echo   Open: http://localhost:7999
echo.
pause