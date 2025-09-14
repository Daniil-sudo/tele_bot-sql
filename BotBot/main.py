import random
import psycopg2
from telebot import types, TeleBot, custom_filters
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage

# ------------------- Настройки -------------------
TOKEN = '8405586746:AAF6IcLURol9JGu59wMhHaO9TTdOwHS01yI'
state_storage = StateMemoryStorage()
bot = TeleBot(TOKEN, state_storage=state_storage)
bot.add_custom_filter(custom_filters.StateFilter(bot))

current_quiz_data = {}

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

# ------------------- Состояния -------------------
class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    delete_word = State()

# ------------------- Команды -------------------
class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово 🔙'
    NEXT = 'Дальше ⏭'

# ------------------- Функции -------------------
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
        if not row:
            return None
        target_word, translate_word = row
        cursor.execute(
            'SELECT target_word FROM words WHERE target_word != %s ORDER BY RANDOM() LIMIT %s',
            (target_word, n - 1)
        )
        others = [w[0] for w in cursor.fetchall()]
        return {'target_word': target_word, 'translate_word': translate_word, 'other_words': others}
    except Exception:
        conn.rollback()
        return None

def show_hint(*lines):
    return '\n'.join(lines)

def show_target(data):
    return f"{data['target_word']} -> {data['translate_word']}"

# ------------------- Создание карточек -------------------
@bot.message_handler(commands=['start', 'cards'])
def create_cards(message):
    cid = message.chat.id

    data = get_random_word_with_others()
    if not data:
        bot.send_message(cid, "База слов пуста. Добавьте новые слова через команду 'Добавить слово ➕'")
        return

    buttons = [types.KeyboardButton(data['target_word'])]
    buttons.extend([types.KeyboardButton(w) for w in data['other_words']])
    random.shuffle(buttons)
    buttons.extend([
        types.KeyboardButton(Command.NEXT),
        types.KeyboardButton(Command.ADD_WORD),
        types.KeyboardButton(Command.DELETE_WORD)
    ])
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(*buttons)

    bot.send_message(cid, f"Выбери перевод слова:\n🇷🇺 {data['translate_word']}", reply_markup=markup)

    # Сохраняем данные для текущего задания
    current_quiz_data[cid] = {
        'target_word': data['target_word'],
        'translate_word': data['translate_word'],
        'buttons': buttons
    }

# ------------------- Дальше -------------------
@bot.message_handler(func=lambda m: m.text == Command.NEXT)
def next_cards(message):
    create_cards(message)

# ------------------- Добавление слова -------------------
@bot.message_handler(func=lambda m: m.text == Command.ADD_WORD)
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

    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(types.KeyboardButton(Command.NEXT),
               types.KeyboardButton(Command.ADD_WORD),
               types.KeyboardButton(Command.DELETE_WORD))
    bot.send_message(message.chat.id, "Что делаем дальше?", reply_markup=markup)

# ------------------- Удаление слова -------------------
@bot.message_handler(func=lambda m: m.text == Command.DELETE_WORD)
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

    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(types.KeyboardButton(Command.NEXT),
               types.KeyboardButton(Command.ADD_WORD),
               types.KeyboardButton(Command.DELETE_WORD))
    bot.send_message(message.chat.id, "Что делаем дальше?", reply_markup=markup)

# ------------------- Ответ на карточки -------------------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def message_reply(message):
    cid = message.chat.id
    text = message.text

    # Если пользователь в состоянии добавления/удаления слова — не мешаем
    state = bot.get_state(message.from_user.id, cid)
    if state is not None:
        return

    quiz_data = current_quiz_data.get(cid)
    if not quiz_data:
        bot.send_message(cid, "Нет активного задания. Нажми /start")
        return

    target_word = quiz_data['target_word']
    buttons = quiz_data['buttons']
    markup = types.ReplyKeyboardMarkup(row_width=2)

    if text == target_word:
        hint_text = ["Отлично!❤", show_target(quiz_data)]
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
        hint = show_hint("Допущена ошибка!",
                         f"Попробуй ещё раз вспомнить слово 🇷🇺{quiz_data['translate_word']}")

    bot.send_message(cid, hint, reply_markup=markup)

# ------------------- Запуск бота -------------------
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling(skip_pending=True)
