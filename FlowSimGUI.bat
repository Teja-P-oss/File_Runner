@echo off
set "SCRIPT_DIR=%~dp0Scripts"

echo [FlowSim GUI Setup]

python -c "import flask" 2>NUL
if %errorlevel% neq 0 pip install flask

python -c "import flask_cors" 2>NUL
if %errorlevel% neq 0 pip install flask-cors

echo Starting system...
start "" "%SCRIPT_DIR%\interface.html"
python "%SCRIPT_DIR%\server.py"
