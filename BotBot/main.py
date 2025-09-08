import random
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
import psycopg2


# ------------------- Подключение к БД -------------------
try:
    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="1",
        host="localhost",
        port=5432
    )
    cursor = conn.cursor()
except Exception as e:
    print(f"Ошибка подключения к базе: {e}")
    conn = None
    cursor = None

# ------------------- Функции работы с БД -------------------
def add_word_to_db(target, translate):
    target = target.strip().lower()
    translate = translate.strip()
    try:
        cursor.execute(
            'INSERT INTO words (target_word, translate_word) VALUES (%s, %s)',
            (target, translate)
        )
        conn.commit()
        return True
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False
    except Exception:
        conn.rollback()
        return False

def get_random_word_with_others(n=4):
    try:
        cursor.execute('SELECT target_word, translate_word FROM words ORDER BY RANDOM() LIMIT 1')
        row = cursor.fetchone()
    except Exception:
        conn.rollback()
        return None

    if not row:
        return None

    target_word, translate_word = row
    cursor.execute(
        'SELECT target_word FROM words WHERE target_word != %s ORDER BY RANDOM() LIMIT %s',
        (target_word, n - 1)
    )
    others_rows = cursor.fetchall()
    others = [w[0] for w in others_rows]
    return {
        'target_word': target_word,
        'translate_word': translate_word,
        'other_words': others
    }

# ------------------- Состояния -------------------
class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    delete_word = State()

# ------------------- Команды -------------------
class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'

# ------------------- Вспомогательные функции -------------------
def show_hint(*lines):
    return '\n'.join(lines)

def show_target(data):
    return f"{data['target_word']} -> {data['translate_word']}"

# ------------------- Инициализация бота -------------------
state_storage = StateMemoryStorage()
token_bot = ''
bot = TeleBot(token_bot, state_storage=state_storage)

known_users = []
userStep = {}

# ------------------- Создание карточек -------------------
@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):
    cid = message.chat.id
    if cid not in known_users:
        known_users.append(cid)
        userStep[cid] = 0
        bot.send_message(cid, "Hello, stranger, let's study English...")

    data = get_random_word_with_others()
    if not data:
        bot.send_message(cid, "База слов пуста. Добавьте новые слова через команду Добавить слово ➕")
        return

    # Формируем кнопки
    buttons = [types.KeyboardButton(data['target_word'])]
    buttons.extend([types.KeyboardButton(word) for word in data['other_words']])
    random.shuffle(buttons)

    # Добавляем системные кнопки
    buttons.extend([
        types.KeyboardButton(Command.NEXT),
        types.KeyboardButton(Command.ADD_WORD),
        types.KeyboardButton(Command.DELETE_WORD)
    ])

    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(*buttons)

    bot.send_message(cid, f"Выбери перевод слова:\n🇷🇺 {data['translate_word']}", reply_markup=markup)

    # Сохраняем данные для пользователя
    with bot.retrieve_data(message.from_user.id, cid) as storage:
        storage['target_word'] = data['target_word']
        storage['translate_word'] = data['translate_word']
        storage['buttons'] = buttons

# ------------------- Кнопка "Дальше" -------------------
@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    create_cards(message)

# ------------------- Кнопка "Добавить слово" -------------------
@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def add_word(message):
    cid = message.chat.id
    bot.send_message(cid, "Введи английское слово:")
    bot.set_state(message.from_user.id, MyStates.target_word, cid)

@bot.message_handler(state=MyStates.target_word)
def process_target_word(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['new_target_word'] = message.text.strip()
    bot.send_message(message.chat.id, "Теперь введи перевод:")
    bot.set_state(message.from_user.id, MyStates.translate_word, message.chat.id)

@bot.message_handler(state=MyStates.translate_word)
def process_translate_word(message):
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['new_target_word']
        translate_word = message.text.strip()

        if add_word_to_db(target_word, translate_word):
            bot.send_message(message.chat.id, f"Слово <b>{target_word}</b> добавлено ✅", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, f"Слово <b>{target_word}</b> уже есть в базе ❌", parse_mode="HTML")

    bot.delete_state(message.from_user.id, message.chat.id)

    # Показываем меню действий после добавления слова
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(
        types.KeyboardButton(Command.NEXT),
        types.KeyboardButton(Command.ADD_WORD),
        types.KeyboardButton(Command.DELETE_WORD)
    )
    bot.send_message(message.chat.id, "Что делаем дальше?", reply_markup=markup)

# ------------------- Кнопка "Удалить слово" -------------------
@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def ask_delete_word(message):
    cid = message.chat.id
    bot.send_message(cid, "Введи английское слово, которое хочешь удалить:")
    bot.set_state(message.from_user.id, MyStates.delete_word, cid)

@bot.message_handler(state=MyStates.delete_word)
def process_delete_word(message):
    word_to_delete = message.text.strip().lower()
    try:
        cursor.execute('DELETE FROM words WHERE target_word = %s RETURNING target_word', (word_to_delete,))
        deleted = cursor.fetchone()
        if deleted:
            conn.commit()
            bot.send_message(message.chat.id, f"Слово <b>{word_to_delete}</b> удалено ✅", parse_mode="HTML")
        else:
            bot.send_message(message.chat.id, f"Слово <b>{word_to_delete}</b> не найдено ❌", parse_mode="HTML")
    except Exception:
        conn.rollback()
        bot.send_message(message.chat.id, "Ошибка при удалении слова ❌")

    bot.delete_state(message.from_user.id, message.chat.id)

    # Меню действий
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(
        types.KeyboardButton(Command.NEXT),
        types.KeyboardButton(Command.ADD_WORD),
        types.KeyboardButton(Command.DELETE_WORD)
    )
    bot.send_message(message.chat.id, "Что делаем дальше?", reply_markup=markup)

# ------------------- Основная обработка текста -------------------
@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message):
    text = message.text
    markup = types.ReplyKeyboardMarkup(row_width=2)

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data.get('target_word')
        buttons = data.get('buttons', [])

        if text == target_word:
            hint = show_target(data)
            hint_text = ["Отлично!❤", hint]
            next_btn = types.KeyboardButton(Command.NEXT)
            add_word_btn = types.KeyboardButton(Command.ADD_WORD)
            delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
            markup.add(*(buttons + [next_btn, add_word_btn, delete_word_btn]))
            hint = show_hint(*hint_text)
        else:
            for btn in buttons:
                if btn.text == text:
                    btn.text = text + '❌'
                    break
            markup.add(*buttons)
            hint = show_hint(
                "Допущена ошибка!",
                f"Попробуй ещё раз вспомнить слово 🇷🇺{data.get('translate_word')}"
            )

    bot.send_message(message.chat.id, hint, reply_markup=markup)

# ------------------- Запуск бота -------------------
bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.infinity_polling(skip_pending=True)

