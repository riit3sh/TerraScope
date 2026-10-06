<#
.SYNOPSIS
  Run TerraScope natively on Windows (no Docker).

.DESCRIPTION
  terrascope.cmd setup      create .venv and install Python + frontend dependencies
  terrascope.cmd start      start data-pipeline :8001, ml-models :8002, backend-api :8000, UI :5173
  terrascope.cmd stop       stop the services this checkout started
  terrascope.cmd status     show what is on each port and whether it is healthy
  terrascope.cmd fetch-data [region]  India boundary (~46 MB, needed once). With a region (e.g. tamil-nadu):
                                     a local OSM store and raster tiles for it. 'fetch-data --list' lists regions.
  terrascope.cmd seed-demo  add one FIXTURE report to the saved-reports list (explicit, never automatic)

  A port that already serves the matching healthy TerraScope service is reused.
  A process counts as TerraScope's only if its command line contains this folder's
  path; anything else on a port is reported and never stopped.

  Saved reports live in .local-ui-check\backend.sqlite3 and survive restarts.
  No PostGIS outside Compose: the data-pipeline's spatial archive is skipped,
  and the backend still stores every snapshot.
#>
param(
    # Both positions are explicit: once any parameter has [Parameter()], PowerShell no
    # longer binds the others by position, and 'stop' would silently become $Region.
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'setup', 'fetch-data', 'seed-demo')]
    [string]$Command = 'start',
    [Parameter(Position = 1)]
    [string]$Region = '',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $PSScriptRoot
$RunDir = Join-Path $Root '.local-ui-check'
$LogDir = Join-Path $RunDir 'logs'
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$Vite = Join-Path $Root 'frontend\node_modules\vite\bin\vite.js'
$Url = 'http://localhost:5173'

$Services = @(
    @{ Name = 'data-pipeline'; Port = 8001; Health = '/health'; Dir = 'data-pipeline'; App = 'internal_api:app'; Timeout = 60 }
    @{ Name = 'ml-models'; Port = 8002; Health = '/health'; Dir = 'ml-models'; App = 'pipeline:app'; Timeout = 120 }
    @{ Name = 'backend-api'; Port = 8000; Health = '/api/v1/health'; Dir = 'backend-api\src'; App = 'terrascope_backend_api.main:app'; Timeout = 60
        PythonPath = @($Root, (Join-Path $Root 'backend-api'), (Join-Path $Root 'backend-api\src')) }
    @{ Name = 'frontend'; Port = 5173; Health = '/'; Dir = 'frontend'; Timeout = 60 }
)

function Quote([string]$s) { '"' + $s + '"' }

function Get-PortOwners([int]$Port) {
    $ids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($id in $ids) {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
        if ($p) { $p }
    }
}

function Test-Ours($Proc) {
    # Command line unreadable (another user's process) => not ours.
    $Proc.CommandLine -and $Proc.CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Test-Healthy($Svc) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 -Uri ("http://127.0.0.1:{0}{1}" -f $Svc.Port, $Svc.Health)
        if ($Svc.Name -eq 'frontend') { return $r.Content -match '<title>TerraScope</title>' }
        return (($r.Content | ConvertFrom-Json).service -eq $Svc.Name)
    } catch { return $false }
}

function Describe($Proc) { "{0} (pid {1})" -f $Proc.Name, $Proc.ProcessId }

function Import-DotEnv {
    $file = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $file)) {
        Write-Warning ".env not found; using defaults. Copy .env.example to .env to configure credentials."
        return
    }
    foreach ($line in Get-Content -LiteralPath $file) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $value = $Matches[2]
            if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") { $value = $Matches[1] }
            [Environment]::SetEnvironmentVariable($Matches[1], $value, 'Process')
        }
    }
}

function Set-DefaultEnv([string]$Name, [string]$Value) {
    $current = [Environment]::GetEnvironmentVariable($Name, 'Process')
    # /app/... values are Compose container paths and do not exist here.
    if (-not $current -or $current.StartsWith('/app/')) {
        [Environment]::SetEnvironmentVariable($Name, $Value, 'Process')
    }
}

function Initialize-Env {
    Import-DotEnv
    Set-DefaultEnv 'BACKEND_STORE_PATH' (Join-Path $RunDir 'backend.sqlite3')
    Set-DefaultEnv 'TERRASCOPE_SATELLITE_CACHE_PATH' (Join-Path $RunDir 'satellite_cache.json')
    Set-DefaultEnv 'RERA_SEED_PATH' (Join-Path $Root 'data-pipeline\data\raw\maharera_seed.csv')
    Set-DefaultEnv 'VALUATION_MODEL_PATH' (Join-Path $Root 'valuation\artifacts\land_price_model.joblib')
    Set-DefaultEnv 'NOMINATIM_USER_AGENT' 'terrascope-local-dev/0.1.0'
    Set-DefaultEnv 'TERRASCOPE_DATA_DIR' (Join-Path $Root 'data-cache')
    # Compose service names do not resolve outside Docker.
    $env:DATA_PIPELINE_URL = 'http://127.0.0.1:8001'
    $env:ML_MODELS_URL = 'http://127.0.0.1:8002'
    $env:FRONTEND_URL = $Url
    $env:VITE_BACKEND_API_URL = 'http://localhost:8000'
    if ($env:DATABASE_URL -match '@postgres[:/]') {
        Write-Warning "DATABASE_URL points at the Compose host 'postgres'; ignoring it (PostGIS archive disabled)."
        $env:DATABASE_URL = ''
    }
    $env:PYTHONUNBUFFERED = '1'
}

function Invoke-Setup {
    if (-not (Test-Path -LiteralPath $Py)) {
        Write-Host "Creating .venv with Python 3.11..."
        & py -3.11 -m venv (Join-Path $Root '.venv')
        if ($LASTEXITCODE) { throw "Could not create .venv. Python 3.11 is required (py -3.11)." }
    }
    Write-Host "Installing Python dependencies (first run downloads CPU PyTorch, ~200 MB)..."
    & $Py -m pip install --retries 10 --timeout 180 --extra-index-url https://download.pytorch.org/whl/cpu `
        -r (Join-Path $Root 'backend-api\requirements.txt') `
        -r (Join-Path $Root 'data-pipeline\requirements.txt') `
        -r (Join-Path $Root 'ml-models\requirements.txt')
    if ($LASTEXITCODE) { throw "pip install failed." }
    Write-Host "Installing frontend dependencies from package-lock.json..."
    Push-Location (Join-Path $Root 'frontend')
    try { & npm.cmd ci; if ($LASTEXITCODE) { throw "npm ci failed." } } finally { Pop-Location }
    Write-Host "Setup complete. Next: terrascope.cmd start"
}

function Start-Svc($Svc) {
    $dir = Join-Path $Root $Svc.Dir
    $out = Join-Path $LogDir "$($Svc.Name).out.log"
    $err = Join-Path $LogDir "$($Svc.Name).err.log"
    if ($Svc.Name -eq 'frontend') {
        $exe = (Get-Command node.exe).Source
        $argLine = "$(Quote $Vite) --host 127.0.0.1 --port $($Svc.Port) --strictPort"
    } else {
        $exe = $Py
        # --app-dir puts this checkout's path on the command line, which is how stop recognises it.
        $argLine = "-m uvicorn $($Svc.App) --app-dir $(Quote $dir) --host 127.0.0.1 --port $($Svc.Port) --log-level warning"
    }
    $env:PYTHONPATH = if ($Svc.PythonPath) { $Svc.PythonPath -join ';' } else { '' }
    $p = Start-Process -FilePath $exe -ArgumentList $argLine -WorkingDirectory $dir -WindowStyle Hidden `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $env:PYTHONPATH = ''
    Write-Host ("  started {0} on :{1} (pid {2})" -f $Svc.Name, $Svc.Port, $p.Id)
    $p
}

function Wait-Ready($Svc, $Proc) {
    $deadline = (Get-Date).AddSeconds($Svc.Timeout)
    while ((Get-Date) -lt $deadline) {
        if (Test-Healthy $Svc) { return $true }
        if ($Proc -and $Proc.HasExited) { break }
        Start-Sleep -Milliseconds 700
    }
    Write-Host ("  {0} FAILED to become healthy on :{1}" -f $Svc.Name, $Svc.Port) -ForegroundColor Red
    foreach ($log in "$($Svc.Name).err.log", "$($Svc.Name).out.log") {
        $path = Join-Path $LogDir $log
        if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length) {
            Write-Host "  --- last lines of $path"
            Get-Content -LiteralPath $path -Tail 15 | ForEach-Object { Write-Host "    $_" }
        }
    }
    $false
}

function Invoke-Start {
    if (-not (Test-Path -LiteralPath $Py)) { throw "Missing .venv. Run: terrascope.cmd setup" }
    if (-not (Test-Path -LiteralPath $Vite)) { throw "Missing frontend\node_modules. Run: terrascope.cmd setup" }
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    Initialize-Env

    # Check every port before launching anything, so a conflict never leaves a half-started stack.
    $plan = @{}
    foreach ($svc in $Services) {
        $owners = @(Get-PortOwners $svc.Port)
        if (-not $owners) { $plan[$svc.Name] = 'start'; continue }
        if (Test-Healthy $svc) {
            Write-Host ("  reusing healthy {0} on :{1} ({2})" -f $svc.Name, $svc.Port, (($owners | ForEach-Object { Describe $_ }) -join ', '))
            continue
        }
        $foreign = @($owners | Where-Object { -not (Test-Ours $_) })
        if ($foreign) {
            throw ("Port {0} is in use by {1}, which is not TerraScope's {2}. It was left running; free the port and retry. Nothing was started." -f
                $svc.Port, (($foreign | ForEach-Object { Describe $_ }) -join ', '), $svc.Name)
        }
        Write-Host ("  {0} on :{1} is ours but not healthy yet; waiting" -f $svc.Name, $svc.Port)
        $plan[$svc.Name] = 'wait'
    }

    $started = @{}
    foreach ($svc in $Services) {
        if ($plan[$svc.Name] -eq 'start') { $started[$svc.Name] = Start-Svc $svc }
        elseif ($plan[$svc.Name] -eq 'wait') { $started[$svc.Name] = $null }
    }

    $ok = $true
    foreach ($svc in $Services) {
        if ($started.ContainsKey($svc.Name)) {
            if (Wait-Ready $svc $started[$svc.Name]) { Write-Host "  $($svc.Name) ready" -ForegroundColor Green } else { $ok = $false }
        }
    }
    if (-not $ok) {
        Write-Host "`nSome services failed. Logs: $LogDir   Stop the rest: terrascope.cmd stop" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host "TerraScope is running:  $Url"
    Write-Host "Saved reports:          $env:BACKEND_STORE_PATH"
    Write-Host "Logs:                   $LogDir"
    Write-Host "Stop:                   terrascope.cmd stop"
    if (-not $NoBrowser) { Start-Process $Url }
}

function Invoke-Stop {
    foreach ($svc in $Services) {
        $owners = @(Get-PortOwners $svc.Port)
        if (-not $owners) { Write-Host ("  {0}: not running" -f $svc.Name); continue }
        foreach ($p in $owners) {
            if (-not (Test-Ours $p)) {
                Write-Host ("  {0}: port {1} is held by {2}, not this checkout; left running" -f $svc.Name, $svc.Port, (Describe $p)) -ForegroundColor Yellow
                continue
            }
            # The .venv python.exe is a launcher that spawns the real interpreter; stop both.
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" -ErrorAction SilentlyContinue
            & taskkill.exe /PID $p.ProcessId /T /F | Out-Null
            if ($parent -and (Test-Ours $parent) -and $parent.ExecutablePath -like "$Root\.venv\*") {
                try { & taskkill.exe /PID $parent.ProcessId /T /F 2>$null | Out-Null } catch { }  # already exited with its child
            }
            Write-Host ("  {0}: stopped {1}" -f $svc.Name, (Describe $p))
        }
    }
}

function Invoke-Status {
    foreach ($svc in $Services) {
        $owners = @(Get-PortOwners $svc.Port)
        if (-not $owners) { Write-Host ("  {0,-14} :{1}  not running" -f $svc.Name, $svc.Port); continue }
        $who = ($owners | ForEach-Object { "{0}{1}" -f (Describe $_), $(if (Test-Ours $_) { '' } else { ' [not this checkout]' }) }) -join ', '
        $health = if (Test-Healthy $svc) { 'healthy' } else { 'NOT healthy' }
        Write-Host ("  {0,-14} :{1}  {2}  {3}" -f $svc.Name, $svc.Port, $health, $who)
    }
}

function Invoke-FetchData {
    if (-not (Test-Path -LiteralPath $Py)) { throw "Missing .venv. Run: terrascope.cmd setup" }
    Initialize-Env
    $fetchArgs = @((Join-Path $Root 'data-pipeline\fetch_data.py'), '--data-dir', $env:TERRASCOPE_DATA_DIR)
    if ($Region -eq '--list') { $fetchArgs += '--list' } elseif ($Region) { $fetchArgs += $Region }
    & $Py @fetchArgs
    if ($LASTEXITCODE) { throw "fetch-data failed (see the messages above). Re-running resumes from the files already downloaded." }
    Write-Host "Local data ready. Restart the services to load it: terrascope.cmd stop, then terrascope.cmd start"
}

function Invoke-SeedDemo {
    Initialize-Env
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $env:PYTHONPATH = (@($Root, (Join-Path $Root 'backend-api'), (Join-Path $Root 'ml-models')) -join ';')
    & $Py (Join-Path $Root 'scripts\seed_ui_demo.py')
    if ($LASTEXITCODE) { throw "Seeding failed." }
    Write-Host "Seeded one FIXTURE report (labelled as such) into $env:BACKEND_STORE_PATH"
}

try {
    switch ($Command) {
        'setup' { Invoke-Setup }
        'start' { Invoke-Start }
        'stop' { Invoke-Stop }
        'status' { Invoke-Status }
        'fetch-data' { Invoke-FetchData }
        'seed-demo' { Invoke-SeedDemo }
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
