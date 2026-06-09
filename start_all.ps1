$ErrorActionPreference = "Stop"

# Start all Legal Multi-Agent System services on Windows PowerShell.
# Each service writes stdout/stderr to logs/*.log for easier debugging.

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Get-Command uv -ErrorAction SilentlyContinue) {
    $Exe = "uv"
    $BaseArgs = @("run", "python")
} elseif (Test-Path $VenvPython) {
    $Exe = $VenvPython
    $BaseArgs = @()
} else {
    $Exe = "python"
    $BaseArgs = @()
}

function Start-AgentService {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Module,
        [Parameter(Mandatory = $true)][int]$Port
    )

    Write-Host "Starting $Name on port $Port..."
    $stdout = Join-Path $LogDir "$Name.out.log"
    $stderr = Join-Path $LogDir "$Name.err.log"
    $args = $BaseArgs + @("-m", $Module)

    $process = Start-Process `
        -FilePath $Exe `
        -ArgumentList $args `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    return [pscustomobject]@{
        Name = $Name
        Module = $Module
        Port = $Port
        Pid = $process.Id
        Stdout = $stdout
        Stderr = $stderr
    }
}

$services = @()
$services += Start-AgentService -Name "registry" -Module "registry" -Port 10000
Start-Sleep -Seconds 2

$services += Start-AgentService -Name "tax_agent" -Module "tax_agent" -Port 10102
$services += Start-AgentService -Name "compliance_agent" -Module "compliance_agent" -Port 10103
Start-Sleep -Seconds 3

$services += Start-AgentService -Name "law_agent" -Module "law_agent" -Port 10101
Start-Sleep -Seconds 3

$services += Start-AgentService -Name "customer_agent" -Module "customer_agent" -Port 10100

Write-Host ""
Write-Host "All services requested:"
$services | Format-Table Name, Port, Pid -AutoSize

Write-Host "Logs are in:"
Write-Host "  $LogDir"
Write-Host ""
Write-Host "Wait about 10 seconds, then run:"
Write-Host "  uv run python test_client.py"
Write-Host ""
Write-Host "To stop all services:"
Write-Host "  .\stop_all.ps1"
