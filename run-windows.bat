@echo off
setlocal
cd /d "%~dp0"
set QT_MEDIA_BACKEND=ffmpeg
set RAYON_NUM_THREADS=2
set OMP_NUM_THREADS=2
if exist "runtime\pythonw.exe" (
  if exist "bin\lupin-market-fetch.exe" (
    "bin\lupin-market-fetch.exe" --runtime-check >nul 2>&1
    if errorlevel 1 if exist "MicrosoftEdgeWebview2Setup.exe" (
      echo Preparing market updates. An internet connection may be needed the first time.
      "MicrosoftEdgeWebview2Setup.exe" /silent /install
    )
  )
  start "" "runtime\pythonw.exe" -B -m price_lens %*
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -B -m price_lens %*
  exit /b
)
py -3 -m price_lens %*
