@echo off
title OBERIG Helper Bot
cd /d "E:\програмування\OBERIGHelperBot"

REM Активація віртуального середовища
call venv\Scripts\activate

REM Встановлення залежностей (на випадок оновлень)
pip install -r requirements.txt

REM Запуск бота
python main.py

REM Очікування натискання клавіші після завершення
pause
