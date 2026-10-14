@echo off
rem TerraScope native launcher. Usage: terrascope [setup^|start^|stop^|status^|seed-demo]
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\terrascope.ps1" %*
exit /b %ERRORLEVEL%
