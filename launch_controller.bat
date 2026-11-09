@echo off
setlocal
title Pybricks route editor
cd /d "%~dp0"
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
set "EXISTING_PYTHON=%~dp0HZ\.venv\Scripts\python.exe"
set "TCLTK_PYTHON=%LOCALAPPDATA%\Programs\Python\Python31410\python.exe"

if exist "%VENV_PYTHON%" goto check_dependencies
if exist "%TCLTK_PYTHON%" goto use_tcltk_python
if exist "%EXISTING_PYTHON%" goto check_existing_environment

where py >nul 2>&1
if errorlevel 1 goto use_python
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto use_python
py -3 -m venv "%~dp0.venv"
if errorlevel 1 goto setup_failed
goto install_dependencies

:use_python
where python >nul 2>&1
if errorlevel 1 goto use_existing_python
python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto use_existing_python
python -m venv "%~dp0.venv"
if errorlevel 1 goto setup_failed
goto install_dependencies

:use_tcltk_python
"%TCLTK_PYTHON%" -c "import tkinter; raise SystemExit(not hasattr(tkinter, 'Tk'))" >nul 2>&1
if errorlevel 1 goto setup_failed
"%TCLTK_PYTHON%" -m venv "%~dp0.venv"
if errorlevel 1 goto setup_failed
goto install_dependencies

:use_existing_python
if not exist "%EXISTING_PYTHON%" goto python_missing
"%EXISTING_PYTHON%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto python_version_missing
"%EXISTING_PYTHON%" -m venv "%~dp0.venv"
if errorlevel 1 goto setup_failed

:install_dependencies
echo Preparing the controller environment...
"%VENV_PYTHON%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto python_version_missing
"%VENV_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto setup_failed
goto run_controller

:check_existing_environment
set "VENV_PYTHON=%EXISTING_PYTHON%"
"%VENV_PYTHON%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto use_python
"%VENV_PYTHON%" -c "from importlib.metadata import version; raise SystemExit(version('pybricksdev') != '2.3.2')" >nul 2>&1
if errorlevel 1 goto use_python
goto run_controller

:check_dependencies
"%VENV_PYTHON%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto python_version_missing
"%VENV_PYTHON%" -c "from importlib.metadata import version; raise SystemExit(version('pybricksdev') != '2.3.2')" >nul 2>&1
if errorlevel 1 (
    "%VENV_PYTHON%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
    if errorlevel 1 goto setup_failed
)

:run_controller
echo Starting the Pybricks route editor...
"%VENV_PYTHON%" "%~dp0controller.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

:python_missing
echo Python 3.10 or newer was not found.
echo Install Python 3.10+ or restore the project's HZ\.venv environment.
goto show_error

:python_version_missing
echo This project environment requires Python 3.10 or newer.
goto show_error

:setup_failed
echo Could not prepare the controller environment.
echo Check Python and your internet connection, then try again.

:show_error
pause
exit /b 1
