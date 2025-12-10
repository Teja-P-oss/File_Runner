@echo off
set "SCRIPT_DIR=%~dp0Scripts"

echo [FlowSim GUI Setup]

echo Installing requirements...

python -m pip install -r "%~dp0requirements_py3.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org

echo.
echo Starting system...
start "" "%SCRIPT_DIR%\interface.html"
python "%SCRIPT_DIR%\server.py"
