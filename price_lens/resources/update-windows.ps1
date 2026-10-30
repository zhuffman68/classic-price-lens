param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$committed = $false
$backup = $null
$rootPath = $null
$unpacked = $null
$job = Split-Path -Parent $Plan
function Check-Package($p) {
    $expected = $p.offer.package
    $file = Get-Item -LiteralPath $p.package_path
    if ($file.Length -ne $expected.bytes -or
        (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.sha256) {
        throw 'The downloaded update failed its final checksum check.'
    }
}
try {
    $p = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
    Check-Package $p
    $rootPath = [IO.Path]::GetFullPath($p.root)
    if (-not (Test-Path -LiteralPath (Join-Path $rootPath 'runtime\pythonw.exe'))) { throw 'Lupin installation not found.' }
    if ($p.target -notin @('windows-installer-x64','windows-portable-x64')) { throw 'Wrong Windows update target.' }
    [Console]::Out.WriteLine('{"ready":true}')
    $commit = [Console]::In.ReadLine() | ConvertFrom-Json
    if ($commit.install -ne $true) { exit 1 }
    $null = [Console]::In.ReadToEnd()
    $committed = $true
    Check-Package $p
    if ($p.target -eq 'windows-installer-x64') {
        $setup = Start-Process -FilePath $p.package_path -ArgumentList @('/VERYSILENT','/NORESTART','/SP-') -Wait -PassThru
        if ($setup.ExitCode -notin @(0,3010)) { throw 'The installer could not complete the update.' }
    } else {
        # Stage on the destination volume, so the final directory swaps are
        # renames even for portable copies on another drive.
        $unpacked = $rootPath + '.incoming-' + [guid]::NewGuid().ToString('N')
        Expand-Archive -LiteralPath $p.package_path -DestinationPath $unpacked
        $newRoot = $unpacked
        if (-not (Test-Path -LiteralPath (Join-Path $newRoot 'runtime\pythonw.exe'))) {
            $folders = @(Get-ChildItem -LiteralPath $unpacked -Directory)
            if ($folders.Count -ne 1) { throw 'Unexpected portable update layout.' }
            $newRoot = $folders[0].FullName
        }
        if (-not (Test-Path -LiteralPath (Join-Path $newRoot 'price_lens\__init__.py'))) { throw 'Incomplete portable update.' }
        $backup = $rootPath + '.rollback-' + [guid]::NewGuid().ToString('N')
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            try { Move-Item -LiteralPath $rootPath -Destination $backup; break }
            catch { if ($attempt -eq 39) { throw }; Start-Sleep -Milliseconds 250 }
        }
        try { Move-Item -LiteralPath $newRoot -Destination $rootPath }
        catch { Move-Item -LiteralPath $backup -Destination $rootPath; $backup=$null; throw }
    }
    @{ok=$true;version=$p.offer.manifest.version;attempt=(Split-Path -Leaf $job)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $job) 'last-result.json') -Encoding UTF8
    $launchArgs = @('-B','-m','price_lens')
    if ($commit.resume_capture) { $launchArgs += '--capture' }
    Start-Process -FilePath (Join-Path $rootPath 'runtime\pythonw.exe') -ArgumentList $launchArgs -WorkingDirectory $rootPath
} catch {
    if (-not $committed) {
        [Console]::Out.WriteLine((@{error='The update could not be prepared. The current app is still available.'} | ConvertTo-Json -Compress))
    } else {
        @{ok=$false;version=$p.offer.manifest.version;attempt=(Split-Path -Leaf $job)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $job) 'last-result.json') -Encoding UTF8
        if ($rootPath -and (Test-Path -LiteralPath (Join-Path $rootPath 'runtime\pythonw.exe'))) {
            Start-Process -FilePath (Join-Path $rootPath 'runtime\pythonw.exe') -ArgumentList @('-B','-m','price_lens') -WorkingDirectory $rootPath
        }
    }
    exit 1
} finally {
    if ($unpacked -and (Test-Path -LiteralPath $unpacked)) {
        Remove-Item -LiteralPath $unpacked -Recurse -Force -ErrorAction SilentlyContinue
    }
}
