-- Таблица пользователей. Хранит основную информацию о пользователях бота.
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    full_name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'demo', -- Статус подписки: demo, premium, expired
    subscription_until TIMESTAMPTZ, -- Дата окончания премиум-подписки
    daily_message_count INT DEFAULT 0, -- Счетчик сообщений для demo-пользователей
    is_banned BOOLEAN DEFAULT FALSE, -- Флаг блокировки
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица сообщений. Хранит историю диалогов.
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- Роль: user или assistant
    content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица платежей. Логирует все попытки и успешные оплаты.
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    amount INT NOT NULL, -- Сумма в минимальных единицах валюты (копейки, центы, XTR)
    currency VARCHAR(10) NOT NULL, -- Валюта (RUB, XTR)
    payment_method VARCHAR(50) NOT NULL, -- Способ оплаты: stars, cryptocloud
    status VARCHAR(50) NOT NULL, -- Статус: pending, success, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    invoice_id TEXT UNIQUE NOT NULL -- Уникальный ID инвойса от платежной системы (charge_id, uuid)
);

-- Таблица подписок. Хранит историю активаций подписок.
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL, -- Тип подписки, например 'premium'
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица системных промптов.
CREATE TABLE IF NOT EXISTS prompts (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE, -- Активен только один промпт
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица для долгосрочной памяти (резюме диалогов).
CREATE TABLE IF NOT EXISTS user_memory (
    id SERIAL PRIMARY KEY,
    user_id INT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    summary TEXT,
    updated_at TIMESTAMPTZ
);

-- Таблица для рассылок из админ-панели.
CREATE TABLE IF NOT EXISTS mailings (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    button_text VARCHAR(255),
    button_url VARCHAR(255),
    segment VARCHAR(50), -- Сегмент аудитории: all, subscribers, active_7d
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent BOOLEAN DEFAULT FALSE
);

-- Таблица для хранения цен.
CREATE TABLE IF NOT EXISTS prices (
    name VARCHAR(50) PRIMARY KEY, -- Имя продукта, например 'premium_month_stars'
    value INT NOT NULL,           -- Цена в юнитах (рубли для CryptoCloud, XTR для Stars)
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Добавляем начальные значения цен, если они еще не установлены
INSERT INTO prices (name, value) VALUES ('premium_month_stars', 350) ON CONFLICT (name) DO NOTHING;
INSERT INTO prices (name, value) VALUES ('premium_month_crypto', 350) ON CONFLICT (name) DO NOTHING;

-- Индексы для ускорения частых запросов
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_poll ON payments(payment_method, status); -- для опроса cryptocloud
CREATE INDEX IF NOT EXISTS idx_prompts_is_active ON prompts(is_active);
CREATE INDEX IF NOT EXISTS idx_mailings_sent ON mailings(sent);