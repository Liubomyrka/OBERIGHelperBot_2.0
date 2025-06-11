@echo off
title Зупинка OBERIG Helper Bot
REM Перехід до директорії, в якій знаходиться скрипт
cd /d "%~dp0"

REM Знаходимо та закриваємо процеси Python, пов'язані з ботом
echo Пошук та закриття процесів Python...
for /f "tokens=1" %%a in ('wmic process where "name='python.exe' and commandline like '%%main.py%%'" get processid') do (
    if "%%a" neq "ProcessId" (
        taskkill /PID %%a /F
        echo Зупинено процес з PID: %%a
    )
)

echo Бот зупинений.
pause
