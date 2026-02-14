@echo off
title OBERIG Helper Bot
REM Перехід до директорії, в якій знаходиться скрипт
cd /d "%~dp0"

REM Запуск бота
python main.py

REM Очікування натискання клавіші після завершення
pause
