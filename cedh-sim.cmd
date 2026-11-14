@echo off
rem cedh-sim launcher for Windows Command Prompt: cedh-sim run 120
cd /d "%~dp0"
where py >nul 2>nul && (py -m cedh_sim %*) || (python -m cedh_sim %*)
