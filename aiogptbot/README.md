# aiogptbot — Telegram AI-бот на aiogram 3 + OpenAI GPT-4o

## Описание

Многофункциональный Telegram-бот с поддержкой:
- Интеграции с OpenAI GPT-4o (диалог по промпту, память, summary)
- Подписок (demo/premium/expired), лимитов, оплаты через Telegram Payments
- Эмпатии, фильтрации мата и эмоций
- Админки (рассылки, промпты, статистика, управление пользователями, выгрузка CSV)
- Логирования (loguru), хранения данных в PostgreSQL и Redis

---

## Структура проекта

```
aiogptbot/
  bot/
    config.py           # Конфигурация и переменные окружения
    main.py             # Точка входа, запуск бота
    logging_config.py   # Логирование
    middlewares.py      # Middleware: логирование, лимиты, фильтрация, антифлуд
    filters.py          # Фильтры: админ, эмоции, мат, подписка
    handlers/
      user.py           # Пользовательские команды и диалог
      admin.py          # Админка: рассылки, промпты, статистика, пользователи
      payments.py       # Оплата: Telegram Payments, Stripe/ЮKassa, крипта
    services/
      openai_service.py     # Интеграция с OpenAI GPT-4o
      memory_service.py     # Короткая и долгосрочная память
      emotion_service.py    # Анализ эмоций, фильтрация, эмпатия
      subscription_service.py # Подписки, лимиты
      mailing_service.py    # Рассылки по сегментам
    models/
      user.py, prompt.py, message.py # Pydantic-модели
    db/
      postgres.py         # Асинхронный пул PostgreSQL
      redis_client.py     # Асинхронный клиент Redis
    utils/
      csv_export.py       # Экспорт пользователей в CSV
    migrations/
      001_init.sql        # SQL-миграция для создания БД
requirements.txt
README.md
```

---

## Быстрый старт

1. **Клонируйте репозиторий и создайте структуру:**

```bash
# (если структура не создана)
mkdir -p aiogptbot/bot/{handlers,services,models,db,migrations,utils} && \
touch aiogptbot/bot/{__init__.py,config.py,main.py,keyboards.py,middlewares.py,filters.py,logging_config.py,utils.py} && \
touch aiogptbot/bot/handlers/{__init__.py,user.py,admin.py,payments.py} && \
touch aiogptbot/bot/services/{__init__.py,openai_service.py,memory_service.py,emotion_service.py,subscription_service.py,mailing_service.py} && \
touch aiogptbot/bot/models/{__init__.py,user.py,prompt.py,message.py} && \
touch aiogptbot/bot/db/{__init__.py,postgres.py,redis_client.py} && \
touch aiogptbot/bot/utils/csv_export.py && \
touch aiogptbot/requirements.txt && \
touch aiogptbot/README.md
```

2. **Установите зависимости:**

```bash
pip install -r requirements.txt
```

3. **Создайте .env файл:**

```
BOT_TOKEN=ваш_токен_бота
OPENAI_API_KEY=ваш_ключ_openai
POSTGRES_DSN=postgresql://user:password@localhost:5432/aiogptbot
REDIS_DSN=redis://localhost:6379/0
ADMIN_IDS=123456789,987654321
```

4. **Создайте БД и примените миграцию:**

```bash
psql -U <user> -d <db> -f bot/migrations/001_init.sql
```

5. **Запустите бота:**

```bash
python -m bot.main
```

---

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота
- `OPENAI_API_KEY` — API-ключ OpenAI
- `POSTGRES_DSN` — строка подключения к PostgreSQL
- `REDIS_DSN` — строка подключения к Redis
- `ADMIN_IDS` — список Telegram ID админов через запятую

---

## Основной функционал

### Пользователь
- `/start` — регистрация, приветствие
- `/profile` — статус, подписка, лимиты
- Диалог с AI (GPT-4o): память, summary, задержки, эмпатия, фильтрация
- 5 сообщений в день (demo), далее — подписка
- Premium: неограниченно
- Оплата: Telegram Payments (основной), Stripe/ЮKassa, крипта (заготовки)

### Админка
- `/get_prompt` — текущий промпт
- `/set_prompt` — изменить промпт
- `/history_prompt` — история промптов
- `/restore_prompt_N` — восстановить промпт по номеру
- `/mailing` — рассылка по сегментам (все, подписчики, активные 7д)
- `/stats` — статистика (все, подписчики, активные, оплаты, средняя длина диалога)
- `/download_csv` — выгрузка пользователей в CSV
- `/find_user` — поиск пользователя по username/ID
- `/ban_user`, `/unban_user` — бан/разбан
- `/test_prompt` — тестовый запрос к GPT
- `/restart_bot` — перезапуск

---

## Память и summary
- Короткая память: 10 последних сообщений
- Долгосрочная: summary (обновляется каждые 10 сообщений через GPT)
- Хранение: Redis (основное), PostgreSQL (резерв)

---

## Логирование
- Все действия логируются через loguru (файл bot.log, ротация 10MB/10 дней)

---

## Миграции
- SQL-файл для создания всех таблиц: `bot/migrations/001_init.sql`

---

## Экспорт пользователей
- `/download_csv` — выгрузка всех пользователей в CSV для админа

---

## Поддержка и доработка
- Для интеграции Stripe/ЮKassa, крипты, кастомных функций — пишите в issues или напрямую разработчику.

## Запуск админ-бота

1. Получите отдельный токен для админ-бота у @BotFather и добавьте его в .env как `ADMIN_BOT_TOKEN`.
2. Запустите админ-бота:

```bash
python -m aiogptbot.adminbot.main
```

- Админ-бот использует те же БД и Redis, что и основной бот.
- Все админские функции (рассылки, промпты, статистика, выгрузка CSV, управление пользователями) теперь доступны только через админ-бота.
- Основной бот работает только с пользователями.
