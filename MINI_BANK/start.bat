@echo off
chcp 65001 >nul
echo ========================================
echo   MINI BANK - Telegram Bot
echo ========================================
echo.

if not exist .env (
    echo [!] Файл .env не найден.
    echo     Скопируйте .env.example в .env и заполните BOT_TOKEN и OWNER_ID.
    pause
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo Starting bot...
python bot.py

pause
