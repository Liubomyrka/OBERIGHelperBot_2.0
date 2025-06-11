@echo off
title OBERIG Helper Bot
REM Перехід до директорії, в якій знаходиться скрипт
cd /d "%~dp0"

REM Активація віртуального середовища
call venv\Scripts\activate

REM Встановлення залежностей (на випадок оновлень)
pip install -r requirements.txt

REM Запуск бота
python main.py

REM Очікування натискання клавіші після завершення
pause
