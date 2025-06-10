# PowerShell скрипт для зупинки OBERIG Helper Bot

# Встановлення політики виконання скриптів
Set-ExecutionPolicy RemoteSigned -Scope Process

# Знаходимо та закриваємо процеси Python, пов'язані з ботом
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -like "*main.py*" }

if ($pythonProcesses) {
    foreach ($process in $pythonProcesses) {
        Write-Host "Зупинено процес з PID: $($process.Id)"
        Stop-Process -Id $process.Id -Force
    }
    Write-Host "Бот зупинений."
} else {
    Write-Host "Процеси бота не знайдено."
}

Read-Host "Натисніть Enter для закриття"
