@echo off
setlocal
cd /d "%~dp0"
set QT_MEDIA_BACKEND=ffmpeg
set RAYON_NUM_THREADS=2
set OMP_NUM_THREADS=2
if exist "runtime\pythonw.exe" (
  start "" "runtime\pythonw.exe" -B -m price_lens --capture %*
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -B -m price_lens --capture %*
  exit /b
)
py -3 -m price_lens --capture %*
