param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$committed = $false
$backup = $null
$rootPath = $null
$unpacked = $null
$launchAttempted = $false
$failureCode = 'prepare-failed'
$Plan = [IO.Path]::GetFullPath($Plan)
$job = Split-Path -Parent $Plan

function Write-UpdateResult([bool]$Ok, [string]$Status, [string]$Reason = '') {
    $record = @{ok=$Ok;status=$Status;version=$p.offer.manifest.version;attempt=(Split-Path -Leaf $job)}
    if ($Reason -like 'startup-*') { $record.reason = 'startup'; $record.detail = $Reason.Substring(8) }
    elseif ($Reason) { $record.reason = $Reason }
    $destination = Join-Path (Split-Path -Parent $job) 'last-result.json'
    $temporary = Join-Path $job ('result-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, ($record | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($destination)) { [IO.File]::Replace($temporary, $destination, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $destination) }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function Wait-StartupReceipt {
    param(
        [Parameter(Mandatory=$true)]$Process,
        [Parameter(Mandatory=$true)][string]$Version,
        [Parameter(Mandatory=$true)][string]$Token,
        [Parameter(Mandatory=$true)][string]$Job,
        [ValidateRange(0.01,20.0)][double]$TimeoutSeconds = 20.0
    )
    $receiptPath = Join-Path $Job 'started.json'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $Process.Refresh()
            if ($Process.HasExited) { return 'startup-exited' }
        } catch { return 'startup-process-unavailable' }
        if (Test-Path -LiteralPath $receiptPath) {
            try {
                $file = Get-Item -LiteralPath $receiptPath
                if ($file.PSIsContainer -or $file.Length -gt 8192) { return 'startup-receipt-invalid' }
                $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $validPid = (($receipt.pid -is [int]) -or ($receipt.pid -is [long])) -and
                    ([long]$receipt.pid -gt 0) -and ([long]$receipt.pid -eq [long]$Process.Id)
                if (-not (($receipt.token -is [string]) -and ($receipt.token -ceq $Token) -and
                    ($receipt.version -is [string]) -and ($receipt.version -ceq $Version) -and $validPid -and
                    ($receipt.ready -is [bool]))) { return 'startup-receipt-invalid' }
                if (-not $receipt.ready) { return 'startup-not-ready' }
                # A matching receipt alone does not prove the launched process
                # survived startup, nor may a late receipt cross the deadline.
                if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) { return 'startup-timeout' }
                $Process.Refresh()
                if ($Process.HasExited) { return 'startup-exited' }
                return $null
            } catch { return 'startup-receipt-invalid' }
        }
        $remaining = ($TimeoutSeconds - $timer.Elapsed.TotalSeconds) * 1000
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Min(200, [Math]::Ceiling($remaining))) }
    }
    return 'startup-timeout'
}

function Check-Package($p) {
    $expected = $p.offer.package
    $file = Get-Item -LiteralPath $p.package_path
    if ($file.Length -ne $expected.bytes -or
        (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.sha256) {
        throw 'The downloaded update failed its final checksum check.'
    }
}
try {
    # PowerShell's provider location and the native process cwd are independent.
    # Neither may keep a handle inside the installation during replacement.
    Set-Location -LiteralPath $job
    [Environment]::CurrentDirectory = $job
    $p = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
    Check-Package $p
    $rootPath = [IO.Path]::GetFullPath($p.root)
    $rootPrefix = $rootPath.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ($job.Equals($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
        $job.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid update workspace.' }
    if (-not (Test-Path -LiteralPath (Join-Path $rootPath 'runtime\pythonw.exe'))) { throw 'Lupin installation not found.' }
    if ($p.target -notin @('windows-installer-x64','windows-portable-x64')) { throw 'Wrong Windows update target.' }
    if (($p.startup_token -isnot [string]) -or ($p.startup_token -cnotmatch '^[0-9a-f]{64}$') -or
        ($p.offer.manifest.version -isnot [string]) -or (-not $p.offer.manifest.version) -or
        ($p.offer.manifest.version.Length -gt 96)) { throw 'Invalid startup receipt identity.' }
    [Console]::Out.WriteLine('{"ready":true}')
    $commit = [Console]::In.ReadLine() | ConvertFrom-Json
    if ($commit.install -ne $true) { exit 1 }
    $null = [Console]::In.ReadToEnd()
    $committed = $true
    $failureCode = 'package-check-failed'
    Check-Package $p
    $failureCode = 'installer-failed'
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
    $failureCode = 'startup-launch-failed'
    $receiptPath = Join-Path $job 'started.json'
    if (Test-Path -LiteralPath $receiptPath) { Remove-Item -LiteralPath $receiptPath -Force }
    Write-UpdateResult $false 'starting'
    $launchArgs = @('-B','-m','price_lens')
    if ($commit.resume_capture) { $launchArgs += '--capture' }
    $previousJob = [Environment]::GetEnvironmentVariable('LUPIN_UPDATE_JOB', 'Process')
    $previousToken = [Environment]::GetEnvironmentVariable('LUPIN_UPDATE_TOKEN', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_JOB', $job, 'Process')
        [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_TOKEN', $p.startup_token, 'Process')
        $launchAttempted = $true
        $launched = Start-Process -FilePath (Join-Path $rootPath 'runtime\pythonw.exe') -ArgumentList $launchArgs -WorkingDirectory $rootPath -PassThru
    } finally {
        [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_JOB', $previousJob, 'Process')
        [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_TOKEN', $previousToken, 'Process')
    }
    if ($null -eq $launched) { throw 'The updated app could not be started.' }
    $startupFailure = Wait-StartupReceipt -Process $launched -Version $p.offer.manifest.version -Token $p.startup_token -Job $job
    if ($startupFailure) { $failureCode = $startupFailure; throw 'The updated app did not confirm startup.' }
    Write-UpdateResult $true 'ready'
} catch {
    if (-not $committed) {
        [Console]::Out.WriteLine((@{error='The update could not be prepared. The current app is still available.'} | ConvertTo-Json -Compress))
    } else {
        Write-UpdateResult $false 'failed' $failureCode
        # Never start a duplicate if a new app was already launched but failed
        # its health check. A prelaunch/installer failure may reopen the app.
        if (-not $launchAttempted -and $rootPath -and (Test-Path -LiteralPath (Join-Path $rootPath 'runtime\pythonw.exe'))) {
            $previousJob = [Environment]::GetEnvironmentVariable('LUPIN_UPDATE_JOB', 'Process')
            $previousToken = [Environment]::GetEnvironmentVariable('LUPIN_UPDATE_TOKEN', 'Process')
            try {
                [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_JOB', $null, 'Process')
                [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_TOKEN', $null, 'Process')
                Start-Process -FilePath (Join-Path $rootPath 'runtime\pythonw.exe') -ArgumentList @('-B','-m','price_lens') -WorkingDirectory $rootPath
            } finally {
                [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_JOB', $previousJob, 'Process')
                [Environment]::SetEnvironmentVariable('LUPIN_UPDATE_TOKEN', $previousToken, 'Process')
            }
        }
    }
    exit 1
} finally {
    if ($unpacked -and (Test-Path -LiteralPath $unpacked)) {
        Remove-Item -LiteralPath $unpacked -Recurse -Force -ErrorAction SilentlyContinue
    }
}
