@echo off
setlocal
cd /d "%~dp0"
set RAYON_NUM_THREADS=2
"runtime\python.exe" windows-selftest.py
if errorlevel 1 (
  echo Self-test failed. Keep this window open to review the error.
  pause
  exit /b 1
)
echo All offline package checks passed.
pause
