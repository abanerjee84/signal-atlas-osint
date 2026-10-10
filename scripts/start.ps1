param([switch]$VerifyStartup)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace
$pythonPath = Join-Path $workspace '.venv\Scripts\python.exe'
$vitePath = Join-Path $workspace 'node_modules\vite\bin\vite.js'
$logDirectory = Join-Path $workspace 'data\logs'
$processStatePath = Join-Path $workspace 'data\run\services.json'
$launchId = [guid]::NewGuid().ToString()
$startedProcesses = @()
$startupMutex = $null
$startupLocked = $false

function Test-LocalPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-Component($Name, $Executable, $Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments `
        -WorkingDirectory $workspace -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "$Name.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "$Name.err.log")
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)"
    if (-not $identity) { throw "$Name stopped during startup. Check data\logs." }
    return $identity
}

function Test-ProcessIdentity($Expected, $Actual) {
    return $Actual -and $Actual.ProcessId -eq $Expected.ProcessId -and `
        $Actual.CreationDate.ToUniversalTime().Ticks.ToString() -eq $Expected.CreatedTicks
}

function Get-ProcessIdentity($ProcessInfo) {
    return [pscustomobject]@{
        ProcessId = $ProcessInfo.ProcessId
        CreatedTicks = $ProcessInfo.CreationDate.ToUniversalTime().Ticks.ToString()
    }
}

function Stop-ComponentTree($Expected) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($Expected.ProcessId)" -ErrorAction SilentlyContinue
    if (-not (Test-ProcessIdentity $Expected $current)) { return }
    # The virtual-environment launcher creates a child Python process.
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($Expected.ProcessId)" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        if ($child.CreationDate -ge $current.CreationDate) {
            Stop-ComponentTree (Get-ProcessIdentity $child)
        }
    }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($Expected.ProcessId)" -ErrorAction SilentlyContinue
    if (Test-ProcessIdentity $Expected $current) {
        Stop-Process -Id $Expected.ProcessId -ErrorAction SilentlyContinue
    }
}

function Stop-ExistingServices {
    $allProcesses = @(Get-CimInstance Win32_Process)
    $protectedIds = @($PID)
    $ancestor = $allProcesses | Where-Object { $_.ProcessId -eq $PID }
    while ($ancestor -and $ancestor.ParentProcessId -and $ancestor.ParentProcessId -notin $protectedIds) {
        $protectedIds += $ancestor.ParentProcessId
        $ancestor = $allProcesses | Where-Object { $_.ProcessId -eq $ancestor.ParentProcessId }
    }
    $targets = @()
    # This also finds services launched before process-state tracking was added.
    foreach ($process in $allProcesses) {
        $command = [string]$process.CommandLine
        if ($command.Replace('/', '\').IndexOf($workspace + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $command -match 'backend\.main:app|\bbackend\.worker\b|vite[\\/]bin[\\/]vite\.js|scripts[\\/]start\.ps1') {
            $targets += Get-ProcessIdentity $process
        }
    }
    if (Test-Path -LiteralPath $processStatePath) {
        try {
            $saved = Get-Content -LiteralPath $processStatePath -Raw | ConvertFrom-Json
            $targets += @($saved.processes)
        } catch {
            Write-Host 'Previous service record was unreadable; checking project processes instead.'
        }
    }
    $targets = @($targets | Where-Object { $_.ProcessId -notin $protectedIds } | Sort-Object ProcessId -Unique)
    if ($targets.Count -gt 0) { Write-Host 'Stopping existing dashboard services...' }
    foreach ($target in $targets) { Stop-ComponentTree $target }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $remaining = @($targets | Where-Object {
            Test-ProcessIdentity $_ (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.ProcessId)" -ErrorAction SilentlyContinue)
        })
        if ($remaining.Count -eq 0) { break }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    if ($remaining.Count -gt 0) { throw 'Could not stop the previous dashboard services.' }
}

function Save-ServiceState {
    $allProcesses = @(Get-CimInstance Win32_Process)
    $owned = @($startedProcesses | ForEach-Object { Get-ProcessIdentity $_ })
    do {
        $children = @($allProcesses | Where-Object {
            $_.ParentProcessId -in $owned.ProcessId -and $_.ProcessId -notin $owned.ProcessId
        })
        $owned += @($children | ForEach-Object { Get-ProcessIdentity $_ })
    } while ($children.Count -gt 0)
    [pscustomobject]@{ launcher_id = $launchId; processes = $owned } |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $processStatePath -Encoding UTF8
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Python environment missing. Follow the installation steps in README.md first.'
    }
    if (-not (Test-Path -LiteralPath $vitePath)) {
        throw 'Frontend dependencies missing. Run npm ci as described in README.md first.'
    }
    $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $mutexSuffix = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($workspace.ToLowerInvariant()))).Replace('-', '')
    } finally { $sha.Dispose() }
    $startupMutex = New-Object Threading.Mutex($false, "Local\GlobalOSINTStartup_$mutexSuffix")
    try { $startupLocked = $startupMutex.WaitOne(30000) } catch [Threading.AbandonedMutexException] { $startupLocked = $true }
    if (-not $startupLocked) { throw 'Another dashboard startup is in progress. Try again when it finishes.' }
    Stop-ExistingServices
    # The old processes have stopped. Recover only leases in this checkout's local data directory.
    & $pythonPath -m scripts.recover_worker --after-project-shutdown
    if ($LASTEXITCODE -ne 0) { throw 'Worker recovery failed. Check the local database before starting.' }
    foreach ($port in @(8000, 5173)) {
        if (Test-LocalPort $port) {
            throw "Port $port is used by a different application. Close that application or change its port."
        }
    }
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $processStatePath) -Force | Out-Null

    # Development server: no build step, so edits to src/ are served immediately.
    # `npm run build` + `npm run preview` still reproduces the production bundle.
    Write-Host 'Starting the API, feed collector, and dashboard (live reload)...'
    $startedProcesses += Start-Component 'api' $pythonPath @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000')
    $startedProcesses += Start-Component 'worker' $pythonPath @('-m', 'backend.worker')
    $startedProcesses += Start-Component 'frontend' $nodePath @("`"$vitePath`"", '--host', '127.0.0.1', '--port', '5173', '--strictPort')
    Save-ServiceState

    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        foreach ($process in $startedProcesses) {
            $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.ProcessId)"
            if (-not (Test-ProcessIdentity (Get-ProcessIdentity $process) $current)) {
                throw 'A server stopped during startup. Check data\logs.'
            }
        }
        try {
            $health = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/api/health' -UseBasicParsing -TimeoutSec 2
            $page = Invoke-WebRequest -Uri 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 2
            if ($health.StatusCode -eq 200 -and $page.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Startup timed out. Check data\logs.' }
    Save-ServiceState
    $startupMutex.ReleaseMutex()
    $startupLocked = $false
    Write-Host ''
    Write-Host 'Dashboard: http://127.0.0.1:5173/'
    Write-Host 'Logs: data\logs'
    if (-not $VerifyStartup) {
        Start-Process 'http://127.0.0.1:5173/'
        Write-Host 'Edits to src\ are served immediately. Keep this window open while using the dashboard.'
        Read-Host 'Press Enter to stop all three services' | Out-Null
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    foreach ($process in $startedProcesses) {
        Stop-ComponentTree (Get-ProcessIdentity $process)
    }
    if (Test-Path -LiteralPath $processStatePath) {
        try {
            $saved = Get-Content -LiteralPath $processStatePath -Raw | ConvertFrom-Json
            if ($saved.launcher_id -eq $launchId) { Remove-Item -LiteralPath $processStatePath }
        } catch { }
    }
    if ($startupLocked) { $startupMutex.ReleaseMutex() }
    if ($startupMutex) { $startupMutex.Dispose() }
    if ($startedProcesses.Count -gt 0) { Write-Host 'Dashboard services stopped.' }
}
