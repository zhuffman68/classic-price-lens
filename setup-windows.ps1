$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path "vendor/minerva/.git")) {
    git clone https://github.com/itechify/minerva.git vendor/minerva
    if ($LASTEXITCODE -ne 0) { throw "Minerva download failed" }
    git -C vendor/minerva checkout --detach 7e1aa7d418fb255bd66eb4dce848fc9eb305cd81
}
$revision = git -C vendor/minerva rev-parse HEAD
if ($revision -ne "7e1aa7d418fb255bd66eb4dce848fc9eb305cd81") { throw "Unexpected Minerva revision" }
py -3 -m venv .venv
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed" }
cargo build --locked --release --manifest-path reader/Cargo.toml -j 2
if ($LASTEXITCODE -ne 0) { throw "Screen-reader build failed" }
& .venv/Scripts/python.exe scripts/build_market_helpers.py windows
if ($LASTEXITCODE -ne 0) { throw "Market-helper build failed; run setup from a Visual Studio Developer PowerShell" }
Write-Host "Ready. Run run-windows.bat. No administrator privileges or game access required."
