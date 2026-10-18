<#
  Instalador del agente en Windows. Abre PowerShell COMO ADMINISTRADOR.

    .\install_agent.ps1 -HubUrl "http://IP-DEL-HUB:8700" -Token "xxxx"

  Crea una tarea programada que arranca el agente al encender el equipo,
  con la cuenta SYSTEM, sin ventana. Idempotente: puedes relanzarlo.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$HubUrl,
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$NodeId = $env:COMPUTERNAME.ToLower(),
  [int]$Interval = 20,
  [int]$ShareCpuPct = 50,
  [int]$ShareRamMb = 2048,
  [string]$WorkerUnit = ""
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
      ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw "Abre PowerShell como Administrador."
}

# --- Python ---------------------------------------------------------------
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue) }
if (-not $py) {
  throw "Falta Python. Instalalo con:  winget install -e --id Python.Python.3.12  y repite."
}
$pyExe = $py.Source

# psutil es opcional, pero en Windows es lo que permite leer el % de CPU.
& $pyExe -m pip install --quiet --disable-pip-version-check psutil 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning "No se pudo instalar psutil: el panel mostrara la CPU como 's/d'." }

# --- Ficheros -------------------------------------------------------------
$dest = "C:\Program Files\dashboard-connector"
$state = "C:\ProgramData\dashboard-connector"
New-Item -ItemType Directory -Force -Path $dest, $state | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "dc_agent.py") (Join-Path $dest "dc_agent.py")

# El .cmd lleva el token: lo dejamos legible solo para administradores.
$cmd = @"
@echo off
set DC_HUB_URL=$HubUrl
set DC_AGENT_TOKEN=$Token
set DC_NODE_ID=$NodeId
set DC_INTERVAL=$Interval
set DC_SHARE_CPU_PCT=$ShareCpuPct
set DC_SHARE_RAM_MB=$ShareRamMb
set DC_WORKER_UNIT=$WorkerUnit
set DC_STATE_DIR=$state
"$pyExe" "$dest\dc_agent.py" >> "$state\agent.log" 2>&1
"@
$runner = Join-Path $dest "run_agent.cmd"
Set-Content -Path $runner -Value $cmd -Encoding ASCII

icacls $runner /inheritance:r /grant:r "SYSTEM:(RX)" "Administrators:(F)" | Out-Null

# --- Tarea programada -----------------------------------------------------
$taskName = "DashboardConnectorAgent"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $runner
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
              -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal `
  -Description "Agente Dashboard Connector: informa CPU/RAM al hub" | Out-Null

Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Listo. Equipo '$NodeId' instalado y arrancado." -ForegroundColor Green
Write-Host "Log:    $state\agent.log"
Write-Host "Estado: Get-ScheduledTask -TaskName $taskName"
Write-Host "Aparecera en el panel en modo 'Fuera' hasta que le cambies el modo."
