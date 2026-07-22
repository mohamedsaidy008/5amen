@echo off
title Mythikra Multi-Bot Concurrent System
echo =================================================
echo       Starting Mythikra Game & Welcome Bots...
echo =================================================
echo.
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The bot system crashed or failed to start.
    echo Make sure Python and aiogram are installed properly.
)
echo.
pause
