# 1. Используем официальный образ Python
FROM python:3.12-slim

# 2. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 3. Устанавливаем зависимости, чтобы избежать их переустановки при каждом изменении кода
# Сначала копируем только файл с зависимостями
COPY requirements.txt .

# Устанавливаем системные зависимости, которые могут понадобиться, и зависимости Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    # gcc и libpq-dev нужны для компиляции psycopg2 (драйвер PostgreSQL)
    gcc \
    libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    # Очищаем кэш apt, чтобы уменьшить размер образа
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 4. Копируем весь код проекта в рабочую директорию
COPY . .

# 5. Указываем команду для запуска бота
# Используем -u для того, чтобы вывод Python не буферизировался и логи сразу попадали в Docker
CMD ["python", "-u", "-m", "aiogptbot.bot.main"] 