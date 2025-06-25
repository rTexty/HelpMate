#!/bin/bash
# Остановить все процессы основного бота
pkill -f 'aiogptbot.bot.main'
# Подождать секунду для надёжности
sleep 1
# Запустить user-бота в фоне
nohup python -m aiogptbot.bot.main > userbot.log 2>&1 & 