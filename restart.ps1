$ErrorActionPreference='Stop'
$projectRoot=$PSScriptRoot
# Only stop this project's Python services; keep PostgreSQL and the frontend running.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -like "*$projectRoot*manage.py*runserver*8001*" -or $_.CommandLine -like "*$projectRoot*manage.py*notification_worker*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
& (Join-Path $projectRoot 'start.ps1')
