run:
	python -m aiogptbot.bot.main &
	python -m aiogptbot.adminbot.main &
	wait

restart_userbot:
	./restart_userbot.sh

break:
	pkill -f 'aiogptbot.bot.main'
	pkill -f 'aiogptbot.adminbot.main'
