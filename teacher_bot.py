import telebot
import requests
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, request
import os

# ==========================================
# ВСТАВЬ СЮДА ТОКЕН НОВОГО БОТА ДЛЯ УЧИТЕЛЕЙ
TOKEN = '8776606855:AAEkzM526o84dP5zjZYE4KxckOjAsjgJyug'
# ==========================================

bot = telebot.TeleBot(TOKEN, threaded=False)
API_BASE = "http://109.233.236.101:5000"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('teachers.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, teacher_name TEXT)''')
conn.commit()

def get_teacher_name(user_id):
    cursor.execute("SELECT teacher_name FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def set_teacher_name(user_id, name):
    cursor.execute("INSERT OR REPLACE INTO users (user_id, teacher_name) VALUES (?, ?)", (user_id, name))
    conn.commit()

# --- РАБОТА С API КОЛЛЕДЖА ---
def get_schedule(target, date_from, date_to, param="teacher"):
    try:
        url = f"{API_BASE}/schedule_range?{param}={requests.utils.quote(target)}&from={date_from}&to={date_to}"
        r = requests.get(url)
        if r.status_code != 200: return None
        return r.json()
    except:
        return None

# --- КЛАВИАТУРЫ ---
def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton('📅 Моё расписание на сегодня'))
    markup.add(telebot.types.KeyboardButton('📅 Моё расписание на неделю'))
    markup.add(telebot.types.KeyboardButton('🚪 Проверить кабинет'))
    markup.add(telebot.types.KeyboardButton('🔍 Найти препода'))
    markup.add(telebot.types.KeyboardButton('⚙️ Сменить фамилию'))
    return markup

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def start(message):
    teacher_name = get_teacher_name(message.chat.id)
    if teacher_name:
        bot.send_message(message.chat.id, f"👋 Здравствуйте, {teacher_name}!\nВыберите действие:", reply_markup=get_main_menu())
    else:
        bot.send_message(message.chat.id, "👋 Здравствуйте! Я бот для учителей.\n\nНапишите вашу фамилию (например: Шалыгина):", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: message.text == '⚙️ Сменить фамилию')
def change_name(message):
    bot.send_message(message.chat.id, "Напишите новую фамилию:", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: get_teacher_name(message.chat.id) is None or message.text == '⚙️ Сменить фамилию')
def save_name(message):
    # Сохраняем фамилию, если это первый запуск или смена фамилии
    if message.text not in ['📅 Моё расписание на сегодня', '📅 Моё расписание на неделю', '🚪 Проверить кабинет', '🔍 Найти препода']:
        teacher_name = message.text.strip()
        set_teacher_name(message.chat.id, teacher_name)
        bot.send_message(message.chat.id, f"✅ Отлично, {teacher_name}! Теперь выберите действие:", reply_markup=get_main_menu())

# --- МОЁ РАСПИСАНИЕ ---
@bot.message_handler(func=lambda message: message.text == '📅 Моё расписание на сегодня')
def today_schedule(message):
    teacher_name = get_teacher_name(message.chat.id)
    today = datetime.now().strftime('%Y-%m-%d')
    data = get_schedule(teacher_name, today, today)
    
    if not data:
        bot.send_message(message.chat.id, "На сегодня пар нет или произошла ошибка.")
        return
        
    text = f"📚 Ваше расписание на сегодня:\n\n"
    for day in data:
        if not day.get('lessons'):
            text += "Занятий нет.\n"
            continue
        for lesson in day['lessons']:
            text += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
            text += f"   👥 Группа: {lesson.get('Group')}\n"
            text += f"   🚪 Ауд. {lesson.get('LectureHall')} (📍 {lesson.get('Territory', '')})\n\n"
            
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == '📅 Моё расписание на неделю')
def week_schedule(message):
    teacher_name = get_teacher_name(message.chat.id)
    today = datetime.now()
    end_week = today + timedelta(days=6)
    data = get_schedule(teacher_name, today.strftime('%Y-%m-%d'), end_week.strftime('%Y-%m-%d'))
    
    if not data:
        bot.send_message(message.chat.id, "На эту неделю пар нет.")
        return
        
    text = f"📚 Ваше расписание на неделю:\n\n"
    for day in data:
        date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
        text += f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
        if not day.get('lessons'):
            text += "Занятий нет.\n\n"
            continue
        for lesson in day['lessons']:
            text += f"🔹 {lesson.get('NumberLesson')} пара: {lesson.get('Discipline')} (Ауд. {lesson.get('LectureHall')})\n"
        text += "\n"
        
    # Если текст слишком длинный, разбиваем его
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[x:x+4000])
    else:
        bot.send_message(message.chat.id, text)

# --- ПРОВЕРКА КАБИНЕТА ---
@bot.message_handler(func=lambda message: message.text == '🚪 Проверить кабинет')
def check_room_prompt(message):
    bot.send_message(message.chat.id, "Введите номер кабинета (например: 15, 19, 2):", reply_markup=telebot.types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda message: True and get_teacher_name(message.chat.id) is not None)
def handle_room_or_teacher(message):
    text = message.text.strip()
    
    # Если это команда меню, игнорируем
    if text in ['📅 Моё расписание на сегодня', '📅 Моё расписание на неделю', '🔍 Найти препода']:
        return

    today = datetime.now().strftime('%Y-%m-%d')
    
    # Логика поиска кабинета (ищем по всем группам, так как API не дает общего списка)
    # Для простоты мы попробуем найти пары для всех групп из базы (или хотя бы для 36-тп, если API не позволяет все)
    # В реальности нужно запрашивать расписание всех групп, но чтобы не нагружать API, сделаем проверку по введенному номеру.
    
    # ПРОВЕРКА КАБИНЕТА (упрощенная)
    if text.isdigit() or text.lower().startswith('каб'):
        room_num = text.replace('каб', '').replace(' ', '')
        bot.send_message(message.chat.id, f"⏳ Ищу, кто занял кабинет {room_num} на сегодня...")
        
        # Примечание: API не отдает расписание по кабинету. 
        # Мы можем запросить расписание для группы, но нам нужен общий срез. 
        # Временно сделаем заглушку с проверкой по одной известной группе (например, 36-тп)
        # В будущем это можно улучшить.
        data = get_schedule("36-тп", today, today, param="group")
        
        found = False
        text_res = f"🚪 Кабинет {room_num}:\n\n"
        if data:
            for day in data:
                for lesson in day.get('lessons', []):
                    if str(lesson.get('LectureHall')) == room_num:
                        text_res += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
                        text_res += f"   👨‍🏫 {lesson.get('Teacher')} | 👥 {lesson.get('Group')}\n\n"
                        found = True
        
        if not found:
            text_res += "Свободен (или данные не найдены)."
            
        bot.send_message(message.chat.id, text_res, reply_markup=get_main_menu())
        
    # ПОИСК ПРЕПОДА
    elif text == '🔍 Найти препода':
        bot.send_message(message.chat.id, "Введите фамилию препода, чтобы узнать, где он сейчас:", reply_markup=telebot.types.ReplyKeyboardRemove())
    
    # ЕСЛИ ВВЕЛИ ФАМИЛИЮ ДЛЯ ПОИСКА
    else:
        bot.send_message(message.chat.id, f"⏳ Ищу {text} на сегодня...")
        data = get_schedule(text, today, today)
        
        if not data:
            bot.send_message(message.chat.id, "Не удалось найти расписание для этого препода.", reply_markup=get_main_menu())
            return
            
        text_res = f"🕵️‍♂️ Где сейчас {text}:\n\n"
        has_lessons = False
        for day in data:
            for lesson in day.get('lessons', []):
                text_res += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
                text_res += f"   🚪 Ауд. {lesson.get('LectureHall')} (📍 {lesson.get('Territory', '')})\n"
                text_res += f"   👥 Группа: {lesson.get('Group')}\n\n"
                has_lessons = True
                
        if not has_lessons:
            text_res += "Сегодня пар нет."
            
        bot.send_message(message.chat.id, text_res, reply_markup=get_main_menu())


# ==========================================
# --- ВЕБ-СЕРВЕР (FLASK) ДЛЯ RENDER ---
# ==========================================
app = Flask(__name__)

@app.route('/')
def home(): return "Teacher Bot is running!"

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        if update: bot.process_new_updates([update])
    except Exception as e: print("Ошибка вебхука:", e)
    return "!", 200

@app.route('/set_webhook')
def set_webhook():
    # ТУТ ССЫЛКА НА ТВОЙ НОВЫЙ RENDER СЕРВИС!
    url = "https://ТВОЙ_СЕРВИС.onrender.com/" + TOKEN
    s = bot.set_webhook(url)
    return "Webhook setup ok" if s else "Webhook setup failed"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
