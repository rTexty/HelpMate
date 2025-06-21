pkill -f 'aiogptbot.bot.main'
pkill -f 'aiogptbot.adminbot.main'
sleep 5
nohup python -m aiogptbot.bot.main > userbot.log 2>&1 &
nohup python -m aiogptbot.adminbot.main > adminbot.log 2>&1 &