run:
	python -m aiogptbot.bot.main &
	python -m aiogptbot.adminbot.main &
	wait

r:
	make break
	make run

break:
	pkill -f 'aiogptbot.bot.main'
	pkill -f 'aiogptbot.adminbot.main'

start:
	brew services start redis
	brew services start postgresql

stop: 
	brew services stop redis
	brew services stop postgresql