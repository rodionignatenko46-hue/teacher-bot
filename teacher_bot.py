import telebot
import requests
from datetime import datetime, timedelta
import sqlite3
from flask import Flask, request
import os
import threading

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
def get_groups():
    try:
        r = requests.get(f"{API_BASE}/groups")
        return r.json() if r.status_code == 200 else []
    except:
        return []

# Универсальная функция поиска (скачиваем расписание всех групп и ищем)
def search_everywhere(query, date_from, date_to, search_type="teacher"):
    groups = get_groups()
    if not groups: return None
    
    results = []
    
    # Ограничим количество групп для скорости (можно увеличить)
    # В реальности лучше запрашивать все, но API может не выдержать
    for group in groups:
        try:
            url = f"{API_BASE}/schedule_range?group={requests.utils.quote(group)}&from={date_from}&to={date_to}"
            r = requests.get(url)
            if r.status_code == 200:
                data = r.json()
                for day in data:
                    for lesson in day.get('lessons', []):
                        # Ищем по преподавателю
                        if search_type == "teacher":
                            if query.lower() in lesson.get('Teacher', '').lower():
                                results.append((day['date'], lesson))
                        # Ищем по кабинету
                        elif search_type == "room":
                            if query == str(lesson.get('LectureHall', '')):
                                results.append((day['date'], lesson))
        except:
            continue
            
    return results

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
    if message.text not in ['📅 Моё расписание на сегодня', '📅 Моё расписание на неделю', '🚪 Проверить кабинет', '🔍 Найти препода']:
        teacher_name = message.text.strip()
        set_teacher_name(message.chat.id, teacher_name)
        bot.send_message(message.chat.id, f"✅ Отлично, {teacher_name}! Теперь выберите действие:", reply_markup=get_main_menu())

# --- МОЁ РАСПИСАНИЕ (Ищем по всем группам, так как API не умеет по фамилии) ---
@bot.message_handler(func=lambda message: message.text == '📅 Моё расписание на сегодня')
def today_schedule(message):
    teacher_name = get_teacher_name(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Ищу ваши пары на сегодня (проверяю все группы)...")
    
    today = datetime.now().strftime('%Y-%m-%d')
    results = search_everywhere(teacher_name, today, today, search_type="teacher")
    
    if not results:
        bot.send_message(message.chat.id, "На сегодня пар нет или произошла ошибка.")
        return
        
    text = f"📚 Ваше расписание на сегодня:\n\n"
    for date, lesson in results:
        text += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
        text += f"   👥 Группа: {lesson.get('Group')}\n"
        text += f"   🚪 Ауд. {lesson.get('LectureHall')} (📍 {lesson.get('Territory', '')})\n\n"
            
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda message: message.text == '📅 Моё расписание на неделю')
def week_schedule(message):
    teacher_name = get_teacher_name(message.chat.id)
    bot.send_message(message.chat.id, "⏳ Ищу ваши пары на неделю (это может занять 10-15 секунд)...")
    
    today = datetime.now()
    end_week = today + timedelta(days=6)
    
    results = search_everywhere(teacher_name, today.strftime('%Y-%m-%d'), end_week.strftime('%Y-%m-%d'), search_type="teacher")
    
    if not results:
        bot.send_message(message.chat.id, "На эту неделю пар нет.")
        return
        
    text = f"📚 Ваше расписание на неделю:\n\n"
    current_date = ""
    for date, lesson in results:
        if date != current_date:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            text += f"\n📅 {date_obj.strftime('%d.%m.%Y')}\n"
            current_date = date
            
        text += f"🔹 {lesson.get('NumberLesson')} пара: {lesson.get('Discipline')} (Гр. {lesson.get('Group')}, Ауд. {lesson.get('LectureHall')})\n"
        
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[x:x+4000])
    else:
        bot.send_message(message.chat.id, text)

# --- ПРОВЕРКА КАБИНЕТА ---
@bot.message_handler(func=lambda message: message.text == '🚪 Проверить кабинет')
def check_room_prompt(message):
    bot.send_message(message.chat.id, "Введите номер кабинета (например: 15, 19, 2):", reply_markup=telebot.types.ReplyKeyboardRemove())

# --- ПОИСК ПРЕПОДА ---
@bot.message_handler(func=lambda message: message.text == '🔍 Найти препода')
def find_teacher_prompt(message):
    bot.send_message(message.chat.id, "Введите фамилию препода:", reply_markup=telebot.types.ReplyKeyboardRemove())

# --- ОБЩИЙ ОБРАБОТЧИК ВВОДА (Кабинет или Поиск) ---
@bot.message_handler(func=lambda message: True and get_teacher_name(message.chat.id) is not None)
def handle_search(message):
    text = message.text.strip()
    today = datetime.now().strftime('%Y-%m-%d')

    if text in ['📅 Моё расписание на сегодня', '📅 Моё расписание на неделю']:
        return # Игнорируем, чтобы не ломать меню

    # ПРОВЕРКА КАБИНЕТА (если ввели цифры)
    if text.isdigit() or text.lower().startswith('каб'):
        room_num = text.replace('каб', '').replace(' ', '')
        bot.send_message(message.chat.id, f"⏳ Ищу пары в кабинете {room_num} на сегодня...")
        
        results = search_everywhere(room_num, today, today, search_type="room")
        
        text_res = f"🚪 Кабинет {room_num}:\n\n"
        if results:
            for date, lesson in results:
                text_res += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
                text_res += f"   👨‍🏫 {lesson.get('Teacher')} | 👥 {lesson.get('Group')}\n\n"
        else:
            text_res += "Свободен (или данных нет)."
            
        bot.send_message(message.chat.id, text_res, reply_markup=get_main_menu())
        
    # ПОИСК ПРЕПОДА (если ввели фамилию)
    else:
        bot.send_message(message.chat.id, f"⏳ Ищу {text} на сегодня...")
        results = search_everywhere(text, today, today, search_type="teacher")
        
        if not results:
            bot.send_message(message.chat.id, "Не удалось найти пары для этого препода.", reply_markup=get_main_menu())
            return
            
        text_res = f"🕵️‍♂️ Где сейчас {text}:\n\n"
        for date, lesson in results:
            text_res += f"🔹 Пара {lesson.get('NumberLesson')}: {lesson.get('Discipline')}\n"
            text_res += f"   🚪 Ауд. {lesson.get('LectureHall')} (📍 {lesson.get('Territory', '')})\n"
            text_res += f"   👥 Группа: {lesson.get('Group')}\n\n"
            
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
    # ССЫЛКА НА ТВОЙ СЕРВИС НА RENDER!
    url = "https://teacher-bot-glh2.onrender.com/" + TOKEN
    s = bot.set_webhook(url)
    return "Webhook setup ok" if s else "Webhook setup failed"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
