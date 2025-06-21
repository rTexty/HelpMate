from loguru import logger

logger.add("bot.log", rotation="10 MB", retention="10 days", level="INFO")
