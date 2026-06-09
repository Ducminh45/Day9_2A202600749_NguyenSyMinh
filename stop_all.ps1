$ErrorActionPreference = "SilentlyContinue"

$ports = @(10000, 10100, 10101, 10102, 10103)

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen
    foreach ($connection in $connections) {
        $ownerPid = $connection.OwningProcess
        $process = Get-Process -Id $ownerPid
        Write-Host "Stopping $($process.ProcessName) PID=$ownerPid on port $port"
        Stop-Process -Id $ownerPid -Force
    }
}

Write-Host "Done."
