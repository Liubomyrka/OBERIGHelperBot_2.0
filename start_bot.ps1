# PowerShell скрипт для запуску OBERIG Helper Bot

# Встановлення політики виконання скриптів
Set-ExecutionPolicy RemoteSigned -Scope Process

# Перехід до директорії, в якій знаходиться скрипт
Set-Location $PSScriptRoot

# Активація віртуального середовища
.\venv\Scripts\Activate.ps1

# Встановлення залежностей
pip install -r requirements.txt

# Запуск бота
python main.py

# Очікування натискання клавіші
Read-Host "Натисніть Enter для закриття"
