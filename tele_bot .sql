-- Создание базы данных (если ещё не создана)
CREATE DATABASE english_bot
    WITH OWNER = postgres
    ENCODING = 'UTF8'
    TEMPLATE = template0
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    CONNECTION LIMIT = -1;

-- Подключение к базе
\c english_bot;

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,       -- уникальный идентификатор
    telegram_id BIGINT UNIQUE NOT NULL -- telegram ID пользователя
);

-- Таблица слов
CREATE TABLE IF NOT EXISTS words (
    id SERIAL PRIMARY KEY,
    target_word VARCHAR(255) UNIQUE NOT NULL,   -- иностранное слово
    translate_word VARCHAR(255) NOT NULL       -- перевод
);

-- Таблица связей пользователя со словом
CREATE TABLE IF NOT EXISTS user_word (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    word_id INT REFERENCES words(id) ON DELETE CASCADE,
    UNIQUE(user_id, word_id)  -- чтобы один пользователь не добавлял одно и то же слово дважды
);

-- Добавление стартовых слов
INSERT INTO words (target_word, translate_word)
VALUES 
    ('apple', 'яблоко'),
    ('dog', 'собака'),
    ('house', 'дом'),
    ('car', 'машина'),
    ('book', 'книга')
ON CONFLICT (target_word) DO NOTHING;
