@echo off
title Mythikra Telegram Bot
echo =========================================
echo       Mythikra Bot is Starting...
echo =========================================
echo.
python bot.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] The bot crashed or failed to start.
    echo Make sure Python and aiogram are installed properly.
)
echo.
pause
