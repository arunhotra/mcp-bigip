@echo off
REM BigIP MCP Server Setup Script for Windows
REM This script creates a virtual environment and installs dependencies

echo BigIP MCP Server Setup
echo ======================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

python --version
echo.

REM Ask user for venv tool preference
echo Choose virtual environment tool:
echo 1^) venv ^(standard Python^)
echo 2^) uv ^(modern, faster^)
set /p choice="Enter choice [1-2] (default: 1): "
if "%choice%"=="" set choice=1

echo.

REM Create virtual environment based on choice
if "%choice%"=="2" (
    uv --version >nul 2>&1
    if errorlevel 1 (
        echo Error: uv is not installed. Install from: https://github.com/astral-sh/uv
        exit /b 1
    )

    echo Creating virtual environment with uv...
    uv venv
    set VENV_PATH=.venv
    set ACTIVATE_PATH=.venv\Scripts\activate.bat
) else (
    echo Creating virtual environment with venv...
    python -m venv venv
    set VENV_PATH=venv
    set ACTIVATE_PATH=venv\Scripts\activate.bat
)

echo Virtual environment created at: %VENV_PATH%
echo.

REM Activate and install dependencies
echo Installing dependencies...
call %ACTIVATE_PATH%

if "%choice%"=="2" (
    uv pip install fastmcp
) else (
    pip install -r requirements.txt
)

echo.
echo Setup complete!
echo.
echo To activate the virtual environment, run:
echo   %ACTIVATE_PATH%
echo.
echo To run the server:
echo   python server.py
echo.
echo To verify installation:
echo   fastmcp version
echo.

pause
