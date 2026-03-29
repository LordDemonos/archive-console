<#
.SYNOPSIS
  Stop Archive Console uvicorn listener on a port (narrow match: python + uvicorn + app.main:app).

.DESCRIPTION
  Finds LISTEN sockets on -Port, inspects OwningProcess via WMI/CIM, and stops only processes
  whose executable looks like python and whose command line includes uvicorn and app.main:app.
  Never does Stop-Process -Name python.

.PARAMETER Port
  TCP port (default: from state.json next to this script, else 8756).

.PARAMETER Force
  Kill without confirmation (for ARCHIVE_CONSOLE_REPLACE=1 from batch).

.PARAMETER ListOnly
  Print matching PID(s) and exit 0; do not kill.
#>
param(
    [int] $Port = 0,
    [switch] $Force,
    [switch] $ListOnly
)

$ErrorActionPreference = "Continue"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $here "state.json"
if ($Port -le 0) {
    if (Test-Path -LiteralPath $statePath) {
        $j = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $Port = [int]($j.port)
    }
    if ($Port -le 0) { $Port = 8756 }
}

function Get-SafeArchiveConsolePids {
    param([int] $ListenPort)
    $conns = @(Get-NetTCPConnection -State Listen -LocalPort $ListenPort -ErrorAction SilentlyContinue)
    if ($conns.Count -eq 0) { return @() }
    $ids = $conns | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
    $out = New-Object System.Collections.Generic.List[int]
    foreach ($procId in $ids) {
        try {
            $p = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
            if (-not $p) { continue }
            $exe = [string]$p.ExecutablePath
            $cmd = [string]$p.CommandLine
            if (-not $exe -or -not $cmd) { continue }
            $exeLower = $exe.ToLowerInvariant()
            if (-not ($exeLower -match 'python(|[0-9]+w?)\.exe$')) { continue }
            if ($cmd -notmatch 'uvicorn') { continue }
            if ($cmd -notmatch 'app\.main:app') { continue }
            $out.Add([int]$procId) | Out-Null
        } catch {
            continue
        }
    }
    return , $out.ToArray()
}

$pids = Get-SafeArchiveConsolePids -ListenPort $Port
if ($pids.Count -eq 0) {
    Write-Host "No matching uvicorn (app.main:app) listener on port $Port."
    exit 0
}

Write-Host "Port $Port : candidate PIDs: $($pids -join ', ')"

if ($ListOnly) {
    exit 0
}

if (-not $Force) {
    $ans = Read-Host "Stop these process(es)? [y/N]"
    if ($ans -notmatch '^[yY]') {
        Write-Host "Aborted."
        exit 2
    }
}

foreach ($procId in $pids) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "Stopped PID $procId"
    } catch {
        Write-Warning "Could not stop PID ${procId}: $_"
        exit 1
    }
}

exit 0
