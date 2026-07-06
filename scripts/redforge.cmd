@echo off
REM Run the RedForge CLI from source (no install needed).
setlocal
set "PYTHONPATH=%~dp0..\cli;%PYTHONPATH%"
python -m redforge %*
