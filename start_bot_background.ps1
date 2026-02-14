# Background launcher for OBERIG Helper Bot.
# - No console prompts
# - Prevents duplicate bot instances
# - Writes minimal service log to logs/autostart.log

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$logDir = Join-Path $root "logs"
$logFile = Join-Path $logDir "autostart.log"

if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory -Force | Out-Null
}

function Write-RunLog([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        Add-Content -Path $logFile -Value "$ts $msg" -ErrorAction Stop
    } catch {
        # Never fail bot start because of log file contention.
    }
}

try {
    Set-Location $root

    $existing = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -like "python*" -and
            $_.CommandLine -match "main\.py"
        } |
        Select-Object -First 1

    if ($existing) {
        Write-RunLog "Skip start: bot already running (pid=$($existing.ProcessId))."
        exit 0
    }

    try {
        $proc = Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory $root -WindowStyle Hidden -PassThru
        Write-RunLog "Started bot with python (pid=$($proc.Id))."
        exit 0
    } catch {
        $proc = Start-Process -FilePath "py" -ArgumentList "-3 main.py" -WorkingDirectory $root -WindowStyle Hidden -PassThru
        Write-RunLog "Started bot with py launcher (pid=$($proc.Id))."
        exit 0
    }
} catch {
    Write-RunLog "ERROR: $($_.Exception.Message)"
    exit 1
}
