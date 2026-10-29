$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot '.runtime') | Out-Null
$pgBin = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
$pgData = Join-Path $projectRoot '.runtime\postgres-live'
if ((Test-Path -LiteralPath $pgBin) -and (Test-Path -LiteralPath $pgData)) {
    & $pgBin -D $pgData status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $pgBin -D $pgData -l (Join-Path $projectRoot '.runtime\postgres.log') -o '-p 55432 -h 127.0.0.1' -w start
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the local PostgreSQL database.' }
    }
}
function Test-LocalPort([int]$port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $client.Dispose() }
}
if (-not (Test-LocalPort 8001)) {
    Start-Process -WindowStyle Hidden -FilePath (Join-Path $projectRoot 'venv\Scripts\python.exe') -ArgumentList @('-u','manage.py','runserver','127.0.0.1:8001','--noreload') -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $projectRoot '.runtime\django.log') -RedirectStandardError (Join-Path $projectRoot '.runtime\django-error.log') | Out-Null
}
if (-not (Test-LocalPort 5174)) {
    Start-Process -WindowStyle Hidden -FilePath $env:ComSpec -ArgumentList @('/d','/c','npm run dev') -WorkingDirectory (Join-Path $projectRoot 'frontend') -RedirectStandardOutput (Join-Path $projectRoot '.runtime\frontend.log') -RedirectStandardError (Join-Path $projectRoot '.runtime\frontend-error.log') | Out-Null
}
$workerRunning = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*$projectRoot*manage.py*notification_worker*" } | Select-Object -First 1
if (-not $workerRunning) {
    Start-Process -WindowStyle Hidden -FilePath (Join-Path $projectRoot 'venv\Scripts\python.exe') -ArgumentList @('-u','manage.py','notification_worker','--interval','10') -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $projectRoot '.runtime\notifications.log') -RedirectStandardError (Join-Path $projectRoot '.runtime\notifications-error.log') | Out-Null
}
Write-Output 'FLIP Gig House: http://127.0.0.1:5174/'
Write-Output 'Admin: http://127.0.0.1:8001/admin/'
