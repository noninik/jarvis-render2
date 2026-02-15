from flask import Flask, request, render_template
import os
import json
import requests
import threading
import time
import subprocess
import asyncio
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
RENDER_URL = os.getenv("RENDER_URL", "")

app = Flask(__name__)
user_data = {}

# === ПАПКА ДЛЯ ДАННЫХ ===
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# === РЕЖИМЫ ===
MODES = {
    "helper": {"name": "💬 Помощник", "prompt": "Ты универсальный AI-помощник Jarvis. Отвечай кратко и по делу на русском. Конкретные ответы с примерами.", "emoji": "💬"},
    "business": {"name": "📊 Бизнес-аналитик", "prompt": "Ты бизнес-аналитик Jarvis. Анализируй рынки, конкурентов, тренды. Структурированные ответы с цифрами. На русском.", "emoji": "📊"},
    "content": {"name": "✍️ Контент-менеджер", "prompt": "Ты контент-менеджер Jarvis. Пишешь посты, статьи, рекламу. Живой дерзкий язык без воды. На русском.", "emoji": "✍️"},
    "coder": {"name": "💻 Программист", "prompt": "Ты full-stack разработчик Jarvis. Пишешь чистый рабочий код на Python, JavaScript, HTML. Готовый код. На русском.", "emoji": "💻"},
    "startup": {"name": "📋 Стартап-консультант", "prompt": "Ты стартап-консультант Jarvis. Бизнес-планы, идеи, unit-экономика. На русском.", "emoji": "📋"},
    "research": {"name": "🔍 Исследователь", "prompt": "Ты исследователь рынка Jarvis. Анализируй ниши, тренды, спрос. Конкретные данные. На русском.", "emoji": "🔍"},
    "automate": {"name": "🚀 Автоматизатор", "prompt": "Ты эксперт по автоматизации Jarvis. Скрипты, боты, парсеры. Готовый код на Python. На русском.", "emoji": "🚀"},
    "copywriter": {"name": "📝 Копирайтер", "prompt": "Ты копирайтер Jarvis. Продающие тексты, лендинги, email-рассылки. Формулы AIDA, PAS. На русском.", "emoji": "📝"},
    "coach": {"name": "🎯 Коуч", "prompt": "Ты лайф-коуч Jarvis. Помогаешь ставить цели, планировать, находить мотивацию. На русском.", "emoji": "🎯"},
    "translator": {"name": "🌍 Переводчик", "prompt": "Ты переводчик Jarvis. Переводишь тексты на/с английского. Объясняешь нюансы. На русском.", "emoji": "🌍"},
}

DEFAULT_MODE = "helper"

JARVIS_SYSTEM_PROMPT = """Ты — JARVIS 2.0, продвинутый командный центр для серийного предпринимателя.

ТВОИ РОЛИ:
1. РЫНОЧНЫЙ АНАЛИТИК — Анализируешь боли людей, ищешь прибыльные ниши, оцениваешь конкурентов
2. СТРАТЕГ — Декомпозируешь идеи на спринты (недельные отрезки), создаёшь бизнес-планы
3. МОТИВАТОР — Поддерживаешь пользователя, геймифицируешь процесс

ПРАВИЛА:
- Отвечай конкретно, без воды
- Структура: проблема → решение → следующий шаг
- Для ниш: потенциал, конкуренция, время до MVP, монетизация
- Для планов: недельные спринты с чек-листами
- Отвечай на русском
- Используй эмодзи умеренно

ФОРМАТ БИЗНЕС-ОЦЕНКИ:
📊 Ниша: [название]
🎯 ЦА: [кто]
💰 Монетизация: [как]
⚡ Конкуренция: [низкая/средняя/высокая]
🕐 MVP: [сколько]
📈 TAM: [оценка]
✅ Вердикт: [стоит/нет + почему]

ФОРМАТ СПРИНТА:
🏃 Спринт [N] — Неделя [N]
Цель: [что сделать]
□ Задача 1
□ Задача 2
□ Задача 3
Критерий: [как понять что готово]"""

TEMPLATES = {
    "biz_plan": {"name": "📋 Бизнес-план", "prompt": "Создай детальный бизнес-план. Спроси нишу и бюджет, потом создай план: идея, ЦА, конкуренты, MVP, монетизация, маркетинг, финансы, риски."},
    "content_plan": {"name": "📅 Контент-план", "prompt": "Создай контент-план на 2 недели. Спроси нишу, дай план: дата, тема, формат, хештеги. 3 поста в день."},
    "competitor": {"name": "🔍 Анализ конкурентов", "prompt": "Проведи анализ конкурентов. Спроси нишу, проанализируй 5 конкурентов: сильные и слабые стороны, цены, УТП."},
    "resume": {"name": "📄 Резюме", "prompt": "Помоги составить резюме. Спроси должность и опыт, создай резюме: контакты, о себе, опыт, навыки, образование."},
    "post_pack": {"name": "✍️ Пак постов", "prompt": "Создай 10 постов для соцсетей. Спроси нишу и тон, напиши 10 постов: продающий, развлекательный, экспертный, вовлекающий."},
    "landing": {"name": "🌐 Текст лендинга", "prompt": "Напиши текст лендинга. Спроси продукт, создай: заголовок, проблемы, решение, преимущества, призыв к действию."},
    "email_chain": {"name": "📧 Email-цепочка", "prompt": "Создай 5 писем для прогрева клиента. Спроси нишу, напиши: приветственное, полезное, кейс, оффер, дожим."},
    "swot": {"name": "📊 SWOT-анализ", "prompt": "Проведи SWOT-анализ. Спроси бизнес, разбери: Strengths, Weaknesses, Opportunities, Threats."},
}

MODE_BUTTONS = {
    "💬 Помощник": "helper", "📊 Бизнес": "business", "✍️ Контент": "content",
    "💻 Код": "coder", "📋 Стартап": "startup", "🔍 Исследование": "research",
    "🚀 Автоматизация": "automate", "📝 Копирайтинг": "copywriter",
    "🎯 Коуч": "coach", "🌍 Переводчик": "translator",
}

TEMPLATE_BUTTONS = {
    "📋 Бизнес-план": "biz_plan", "📅 Контент-план": "content_plan",
    "🔍 Анализ конкурентов": "competitor", "📄 Резюме": "resume",
    "✍️ Пак постов": "post_pack", "🌐 Текст лендинга": "landing",
    "📧 Email-цепочка": "email_chain", "📊 SWOT-анализ": "swot",
}


# ============================================================
# УТИЛИТЫ JSON
# ============================================================

def read_json(filename, default=None):
    if default is None:
        default = {}
    filepath = DATA_DIR / filename
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        write_json(filename, default)
        return default


def write_json(filename, data):
    filepath = DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# ГЕЙМИФИКАЦИЯ
# ============================================================

def get_player():
    return read_json("player.json", {
        "level": 1,
        "xp": 0,
        "xp_to_next": 1000,
        "rank": "Новичок",
        "total_projects": 0,
        "completed_quests": 0,
        "streak": 0
    })


def add_xp(amount, reason=""):
    ranks = [
        "Новичок", "Стажёр", "Предприниматель", "Бизнесмен",
        "Стратег", "Магнат", "Титан", "Легенда"
    ]
    player = get_player()
    player["xp"] += amount
    leveled = False
    while player["xp"] >= player["xp_to_next"]:
        player["xp"] -= player["xp_to_next"]
        player["level"] += 1
        player["xp_to_next"] = int(player["xp_to_next"] * 1.3)
        rank_idx = min(player["level"] // 5, len(ranks) - 1)
        player["rank"] = ranks[rank_idx]
        leveled = True
    write_json("player.json", player)
    return player, leveled


# ============================================================
# TELEGRAM USER DATA
# ============================================================

def get_user(chat_id, key, default=""):
    uid = str(chat_id)
    if uid not in user_data:
        user_data[uid] = {}
    return user_data[uid].get(key, default)


def set_user(chat_id, key, value):
    uid = str(chat_id)
    if uid not in user_data:
        user_data[uid] = {}
    user_data[uid][key] = value


def get_context(chat_id):
    return get_user(chat_id, "context", [])


def add_context(chat_id, role, text):
    ctx = get_context(chat_id)
    ctx.append({"role": role, "text": text[:1000]})
    if len(ctx) > 20:
        ctx = ctx[-20:]
    set_user(chat_id, "context", ctx)


def get_mode_prompt(chat_id):
    mode = get_user(chat_id, "mode", DEFAULT_MODE)
    return MODES.get(mode, MODES[DEFAULT_MODE])["prompt"]


def get_favorites(chat_id):
    return get_user(chat_id, "favorites", [])


def add_favorite(chat_id, text):
    favs = get_favorites(chat_id)
    favs.append({"text": text[:500], "date": time.strftime("%d.%m %H:%M")})
    if len(favs) > 20:
        favs = favs[-20:]
    set_user(chat_id, "favorites", favs)


def get_notes(chat_id):
    return get_user(chat_id, "notes", [])


def add_note(chat_id, text):
    notes = get_notes(chat_id)
    notes.append({"text": text[:500], "date": time.strftime("%d.%m %H:%M")})
    if len(notes) > 50:
        notes = notes[-50:]
    set_user(chat_id, "notes", notes)


def get_stats(chat_id):
    return get_user(chat_id, "stats", {"messages": 0, "modes": {}})


def update_stats(chat_id):
    stats = get_stats(chat_id)
    stats["messages"] = stats.get("messages", 0) + 1
    mode = get_user(chat_id, "mode", DEFAULT_MODE)
    modes = stats.get("modes", {})
    modes[mode] = modes.get(mode, 0) + 1
    stats["modes"] = modes
    set_user(chat_id, "stats", stats)


# ============================================================
# ИНСТРУМЕНТЫ
# ============================================================

def search_web(query):
    try:
        from bs4 import BeautifulSoup
        resp = requests.get("https://html.duckduckgo.com/html/", params={"q": query},
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for r in soup.select(".result__body")[:5]:
            t = r.select_one(".result__title")
            s = r.select_one(".result__snippet")
            if t and s:
                results.append(t.get_text().strip() + ": " + s.get_text().strip())
        return "\n\n".join(results) if results else "Ничего не найдено"
    except Exception as e:
        return "Ошибка: " + str(e)


def parse_website(url):
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        lines = [l.strip() for l in soup.get_text().splitlines() if l.strip()]
        return "\n".join(lines[:50])[:2000]
    except Exception as e:
        return "Ошибка: " + str(e)


def generate_image(prompt):
    file_path = f"/tmp/image_{uuid.uuid4().hex[:8]}.jpg"
    urls = [
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=800&height=600&nologo=true&seed={int(time.time())}",
        f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=512&height=512&nologo=true",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=120, stream=True, allow_redirects=True,
                                headers={"User-Agent": "Mozilla/5.0"})
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and "image" in content_type:
                with open(file_path, "wb") as f:
                    for chunk in resp.iter_content(4096):
                        if chunk:
                            f.write(chunk)
                if os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                    return file_path
                if os.path.exists(file_path):
                    os.remove(file_path)
        except:
            continue
    try:
        resp = requests.get("https://picsum.photos/800/600", timeout=30, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 5000:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path
    except:
        pass
    return None


def create_voice(text):
    file_id = uuid.uuid4().hex[:8]
    mp3_path = f"/tmp/voice_{file_id}.mp3"
    ogg_path = f"/tmp/voice_{file_id}.ogg"
    try:
        import edge_tts
        loop = asyncio.new_event_loop()
        try:
            communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural", rate="-10%")
            loop.run_until_complete(communicate.save(mp3_path))
        finally:
            loop.close()
        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 100:
            try:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "64k", ogg_path],
                    timeout=30, capture_output=True
                )
                if result.returncode == 0 and os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 100:
                    os.remove(mp3_path)
                    return ogg_path
            except:
                pass
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
            return mp3_path
    except:
        pass
    for p in [mp3_path, ogg_path]:
        if os.path.exists(p):
            os.remove(p)
    try:
        from gtts import gTTS
        fallback_path = f"/tmp/voice_{file_id}_gtts.mp3"
        tts = gTTS(text=text, lang='ru')
        tts.save(fallback_path)
        if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 100:
            return fallback_path
    except:
        pass
    return None


# ============================================================
# AI ВЫЗОВ (Groq)
# ============================================================

def call_ai(system_prompt, user_message, context):
    messages = [{"role": "system", "content": system_prompt}]
    for msg in context[-10:]:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["text"]})
    messages.append({"role": "user", "content": user_message})
    try:
        resp = requests.post(GROQ_URL, headers={
            "Authorization": "Bearer " + GROQ_API_KEY,
            "Content-Type": "application/json",
        }, json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.9,
            "max_tokens": 3000,
        }, timeout=60)
        if resp.status_code != 200:
            return "AI временно недоступен."
        return resp.json()["choices"][0]["message"]["content"]
    except:
        return "Ошибка соединения с AI."


# ============================================================
# TELEGRAM API
# ============================================================

def send_msg(chat_id, text, reply_kb=None, inline_kb=None):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    sent_ids = []
    while text:
        chunk = text[:4000]
        text = text[4000:]
        payload = {"chat_id": chat_id, "text": chunk}
        if not text and inline_kb:
            payload["reply_markup"] = inline_kb
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                msg_id = resp.json().get("result", {}).get("message_id")
                if msg_id:
                    sent_ids.append(msg_id)
        except:
            pass
    if reply_kb:
        send_reply_kb(chat_id, reply_kb)
    return sent_ids


def send_reply_kb(chat_id, reply_kb):
    try:
        resp = requests.post(
            "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage",
            json={"chat_id": chat_id, "text": "⌨️", "reply_markup": reply_kb},
            timeout=30
        )
        if resp.status_code == 200:
            msg_id = resp.json().get("result", {}).get("message_id")
            if msg_id:
                threading.Thread(target=delete_msg_delayed, args=(chat_id, msg_id, 1), daemon=True).start()
    except:
        pass


def delete_msg(chat_id, message_id):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/deleteMessage",
                       json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
    except:
        pass


def delete_msg_delayed(chat_id, message_id, delay):
    time.sleep(delay)
    delete_msg(chat_id, message_id)


def edit_msg(chat_id, message_id, text, inline_kb=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000]}
    if inline_kb:
        payload["reply_markup"] = inline_kb
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/editMessageText",
                       json=payload, timeout=30)
    except:
        pass


def send_photo(chat_id, file_path, caption=""):
    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption[:1000]},
                    files={"photo": ("image.jpg", f, "image/jpeg")}, timeout=60
                )
                if resp.status_code == 200:
                    return
        send_msg(chat_id, "❌ Не удалось сгенерировать картинку.")
    except:
        send_msg(chat_id, "❌ Ошибка отправки фото.")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


def send_voice(chat_id, file_path):
    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                if file_path.endswith(".ogg"):
                    requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendVoice",
                                  data={"chat_id": chat_id}, files={"voice": f}, timeout=30)
                else:
                    requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendAudio",
                                  data={"chat_id": chat_id, "title": "Озвучка"}, files={"audio": f}, timeout=30)
        else:
            send_msg(chat_id, "❌ Не удалось создать голосовое.")
    except:
        send_msg(chat_id, "❌ Ошибка отправки голосового.")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass


def send_typing(chat_id):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendChatAction",
                       json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except:
        pass


def answer_cb(callback_id, text=""):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/answerCallbackQuery",
                       json={"callback_query_id": callback_id, "text": text}, timeout=10)
    except:
        pass


# ============================================================
# TELEGRAM КЛАВИАТУРЫ
# ============================================================

def main_reply_kb():
    return {"keyboard": [
        ["💬 Помощник", "📊 Бизнес", "✍️ Контент"],
        ["💻 Код", "📋 Стартап", "🔍 Исследование"],
        ["🚀 Автоматизация", "📝 Копирайтинг"],
        ["🎯 Коуч", "🌍 Переводчик"],
        ["📦 Шаблоны", "🛠 Инструменты"],
        ["📌 Избранное", "📝 Заметки", "📊 Статистика"],
    ], "resize_keyboard": True}


def templates_reply_kb():
    return {"keyboard": [
        ["📋 Бизнес-план", "📅 Контент-план"],
        ["🔍 Анализ конкурентов", "📄 Резюме"],
        ["✍️ Пак постов", "🌐 Текст лендинга"],
        ["📧 Email-цепочка", "📊 SWOT-анализ"],
        ["⬅️ Назад в меню"],
    ], "resize_keyboard": True}


def tools_reply_kb():
    return {"keyboard": [
        ["🔍 Поиск", "🌐 Парсинг сайта"],
        ["🖼 Генерация фото", "🎙 Озвучка текста"],
        ["📝 Суммаризация"],
        ["🇬🇧→🇷🇺 Перевод EN-RU", "🇷🇺→🇬🇧 Перевод RU-EN"],
        ["🗑 Очистить контекст"],
        ["⬅️ Назад в меню"],
    ], "resize_keyboard": True}


def after_reply_kb():
    return {"keyboard": [
        ["🔄 Подробнее", "✏️ Переписать"],
        ["📋 Список", "🎯 Пример"],
        ["🖼 Нарисовать", "🎙 Озвучить"],
        ["📌 В избранное", "📝 В заметки"],
        ["🏠 Меню"],
    ], "resize_keyboard": True}


def main_inline_kb():
    return {"inline_keyboard": [
        [{"text": "💬 Помощник", "callback_data": "mode_helper"}, {"text": "📊 Бизнес", "callback_data": "mode_business"}],
        [{"text": "✍️ Контент", "callback_data": "mode_content"}, {"text": "💻 Код", "callback_data": "mode_coder"}],
        [{"text": "📋 Стартап", "callback_data": "mode_startup"}, {"text": "🔍 Исследование", "callback_data": "mode_research"}],
        [{"text": "🚀 Автоматизация", "callback_data": "mode_automate"}, {"text": "📝 Копирайтинг", "callback_data": "mode_copywriter"}],
        [{"text": "🎯 Коуч", "callback_data": "mode_coach"}, {"text": "🌍 Переводчик", "callback_data": "mode_translator"}],
        [{"text": "📦 Шаблоны", "callback_data": "show_templates"}, {"text": "🛠 Инструменты", "callback_data": "show_tools"}],
        [{"text": "📌 Избранное", "callback_data": "show_favs"}, {"text": "📝 Заметки", "callback_data": "show_notes"}],
    ]}


def tpl_inline_kb():
    return {"inline_keyboard": [
        [{"text": "📋 Бизнес-план", "callback_data": "tpl_biz_plan"}],
        [{"text": "📅 Контент-план", "callback_data": "tpl_content_plan"}],
        [{"text": "🔍 Конкуренты", "callback_data": "tpl_competitor"}],
        [{"text": "📄 Резюме", "callback_data": "tpl_resume"}],
        [{"text": "✍️ Пак постов", "callback_data": "tpl_post_pack"}],
        [{"text": "🌐 Лендинг", "callback_data": "tpl_landing"}],
        [{"text": "📧 Email-цепочка", "callback_data": "tpl_email_chain"}],
        [{"text": "📊 SWOT", "callback_data": "tpl_swot"}],
        [{"text": "⬅️ Назад", "callback_data": "back_main"}],
    ]}


def tools_inline_kb():
    return {"inline_keyboard": [
        [{"text": "🔍 Поиск", "callback_data": "tool_search"}, {"text": "🌐 Парсинг", "callback_data": "tool_parse"}],
        [{"text": "🖼 Картинка", "callback_data": "tool_image"}, {"text": "🎙 Голос", "callback_data": "tool_voice"}],
        [{"text": "📝 Суммаризация", "callback_data": "tool_summarize"}],
        [{"text": "🇬🇧→🇷🇺", "callback_data": "tool_enru"}, {"text": "🇷🇺→🇬🇧", "callback_data": "tool_ruen"}],
        [{"text": "🗑 Очистить", "callback_data": "tool_clear"}],
        [{"text": "⬅️ Назад", "callback_data": "back_main"}],
    ]}


def after_inline_kb():
    return {"inline_keyboard": [
        [{"text": "🔄 Подробнее", "callback_data": "act_more"}, {"text": "✏️ Переписать", "callback_data": "act_rewrite"}],
        [{"text": "📋 Список", "callback_data": "act_list"}, {"text": "🎯 Пример", "callback_data": "act_example"}],
        [{"text": "🖼 Картинка", "callback_data": "act_image"}, {"text": "🎙 Озвучить", "callback_data": "act_voice"}],
        [{"text": "📌 В избранное", "callback_data": "act_fav"}, {"text": "📝 В заметки", "callback_data": "act_note"}],
        [{"text": "🏠 Меню", "callback_data": "back_main"}],
    ]}


# ============================================================
# TELEGRAM CALLBACK HANDLER
# ============================================================

def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    cb_id = cb["id"]
    data = cb["data"]
    old_msg_id = cb["message"]["message_id"]

    if data.startswith("mode_"):
        mode_key = data[5:]
        if mode_key in MODES:
            set_user(chat_id, "mode", mode_key)
            set_user(chat_id, "context", [])
            set_user(chat_id, "waiting", "")
            m = MODES[mode_key]
            answer_cb(cb_id, m["name"])
            delete_msg(chat_id, old_msg_id)
            send_msg(chat_id, m["emoji"] + " Режим: " + m["name"] + "\n\nЗадавай вопросы!",
                     reply_kb=after_reply_kb(), inline_kb=after_inline_kb())

    elif data == "show_templates":
        answer_cb(cb_id)
        edit_msg(chat_id, old_msg_id, "📦 Шаблоны:", tpl_inline_kb())
        send_reply_kb(chat_id, templates_reply_kb())

    elif data.startswith("tpl_"):
        key = data[4:]
        if key in TEMPLATES:
            answer_cb(cb_id, TEMPLATES[key]["name"])
            delete_msg(chat_id, old_msg_id)
            send_typing(chat_id)
            update_stats(chat_id)
            answer = call_ai(get_mode_prompt(chat_id), TEMPLATES[key]["prompt"], get_context(chat_id))
            add_context(chat_id, "user", TEMPLATES[key]["prompt"])
            add_context(chat_id, "assistant", answer)
            send_msg(chat_id, answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())

    elif data == "show_tools":
        answer_cb(cb_id)
        edit_msg(chat_id, old_msg_id, "🛠 Инструменты:", tools_inline_kb())
        send_reply_kb(chat_id, tools_reply_kb())

    elif data == "tool_search":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "search")
        send_msg(chat_id, "🔍 Напиши запрос:")

    elif data == "tool_parse":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "parse")
        send_msg(chat_id, "🌐 Отправь ссылку:")

    elif data == "tool_image":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "image")
        send_msg(chat_id, "🖼 Опиши что нарисовать:")

    elif data == "tool_voice":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "voice")
        send_msg(chat_id, "🎙 Напиши текст:")

    elif data == "tool_summarize":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "summarize")
        send_msg(chat_id, "📝 Отправь текст:")

    elif data == "tool_enru":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "enru")
        send_msg(chat_id, "🇬🇧→🇷🇺 Текст:")

    elif data == "tool_ruen":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "ruen")
        send_msg(chat_id, "🇷🇺→🇬🇧 Текст:")

    elif data == "tool_clear":
        answer_cb(cb_id, "Очищено!")
        set_user(chat_id, "context", [])
        edit_msg(chat_id, old_msg_id, "🗑 Очищено!", main_inline_kb())
        send_reply_kb(chat_id, main_reply_kb())

    elif data == "act_more":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Подробнее. Деталей, цифр, примеров.", get_context(chat_id))
        add_context(chat_id, "user", "Подробнее")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_rewrite":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Перепиши лучше.", get_context(chat_id))
        add_context(chat_id, "user", "Переписать")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_list":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Оформи списком.", get_context(chat_id))
        add_context(chat_id, "user", "Списком")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_example":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Пример с цифрами.", get_context(chat_id))
        add_context(chat_id, "user", "Пример")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_image":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        prompt = call_ai("Отвечай ТОЛЬКО промтом без кавычек.",
                         "Короткий промт на английском для картинки по теме последнего сообщения. Максимум 10 слов.",
                         get_context(chat_id))
        prompt = prompt.strip().strip('"').strip("'").strip("`")[:200]
        send_msg(chat_id, f"🎨 Генерирую: {prompt}\n⏳ Подожди...")
        img_path = generate_image(prompt)
        send_photo(chat_id, img_path, "🖼 " + prompt)

    elif data == "act_voice":
        answer_cb(cb_id)
        delete_msg(chat_id, old_msg_id)
        send_typing(chat_id)
        ctx = get_context(chat_id)
        if not ctx:
            send_msg(chat_id, "❌ Нечего озвучивать.")
            return
        send_msg(chat_id, "🎙 Создаю голосовое...")
        voice_path = create_voice(ctx[-1]["text"][:500])
        if voice_path:
            send_voice(chat_id, voice_path)
        else:
            send_msg(chat_id, "❌ Не удалось создать голосовое.")

    elif data == "act_fav":
        answer_cb(cb_id, "📌 Добавлено!")
        ctx = get_context(chat_id)
        if ctx:
            add_favorite(chat_id, ctx[-1]["text"])

    elif data == "act_note":
        answer_cb(cb_id, "📝 Сохранено!")
        ctx = get_context(chat_id)
        if ctx:
            add_note(chat_id, ctx[-1]["text"])

    elif data == "show_favs":
        answer_cb(cb_id)
        favs = get_favorites(chat_id)
        if favs:
            t = "📌 Избранное:\n\n"
            for i, f in enumerate(favs[-10:], 1):
                t += f"{i}. [{f['date']}]\n{f['text'][:200]}\n\n"
            edit_msg(chat_id, old_msg_id, t, main_inline_kb())
        else:
            edit_msg(chat_id, old_msg_id, "📌 Пусто.", main_inline_kb())

    elif data == "show_notes":
        answer_cb(cb_id)
        notes = get_notes(chat_id)
        if notes:
            t = "📝 Заметки:\n\n"
            for i, n in enumerate(notes[-10:], 1):
                t += f"{i}. [{n['date']}]\n{n['text'][:200]}\n\n"
            edit_msg(chat_id, old_msg_id, t, main_inline_kb())
        else:
            edit_msg(chat_id, old_msg_id, "📝 Пусто. /note текст", main_inline_kb())

    elif data == "back_main":
        answer_cb(cb_id)
        mode = get_user(chat_id, "mode", DEFAULT_MODE)
        edit_msg(chat_id, old_msg_id, "🤖 Jarvis 2.0 | " + MODES.get(mode, MODES[DEFAULT_MODE])["name"],
                 main_inline_kb())
        send_reply_kb(chat_id, main_reply_kb())


# ============================================================
# TELEGRAM MESSAGE HANDLER
# ============================================================

def handle_message(chat_id, text):
    text = text.strip()

    if text in ["/start", "/menu", "🏠 Меню", "⬅️ Назад в меню"]:
        send_msg(chat_id, "🤖 Jarvis AI Agent 2.0\n\nВыбери режим или напиши вопрос:",
                 reply_kb=main_reply_kb(), inline_kb=main_inline_kb())
        return

    if text.startswith("/note "):
        note_text = text[6:].strip()
        if note_text:
            add_note(chat_id, note_text)
            send_msg(chat_id, "📝 Сохранено!")
        return

    if text in ["/stats", "📊 Статистика"]:
        stats = get_stats(chat_id)
        msg = f"📊 Статистика:\n\nСообщений: {stats.get('messages', 0)}\n\nРежимы:\n"
        for m, count in stats.get("modes", {}).items():
            msg += f"  {MODES.get(m, {'name': m})['name']}: {count}\n"
        send_msg(chat_id, msg)
        return

    if text in MODE_BUTTONS:
        mode_key = MODE_BUTTONS[text]
        set_user(chat_id, "mode", mode_key)
        set_user(chat_id, "context", [])
        set_user(chat_id, "waiting", "")
        m = MODES[mode_key]
        send_msg(chat_id, m["emoji"] + " Режим: " + m["name"] + "\n\nЗадавай вопросы!",
                 reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if text == "📦 Шаблоны":
        send_msg(chat_id, "📦 Шаблоны:", reply_kb=templates_reply_kb(), inline_kb=tpl_inline_kb())
        return

    if text in TEMPLATE_BUTTONS:
        key = TEMPLATE_BUTTONS[text]
        send_typing(chat_id)
        update_stats(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), TEMPLATES[key]["prompt"], get_context(chat_id))
        add_context(chat_id, "user", TEMPLATES[key]["prompt"])
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if text == "🛠 Инструменты":
        send_msg(chat_id, "🛠 Инструменты:", reply_kb=tools_reply_kb(), inline_kb=tools_inline_kb())
        return

    if text == "🔍 Поиск":
        set_user(chat_id, "waiting", "search"); send_msg(chat_id, "🔍 Запрос:"); return
    if text == "🌐 Парсинг сайта":
        set_user(chat_id, "waiting", "parse"); send_msg(chat_id, "🌐 Ссылка:"); return
    if text == "🖼 Генерация фото":
        set_user(chat_id, "waiting", "image"); send_msg(chat_id, "🖼 Опиши:"); return
    if text == "🎙 Озвучка текста":
        set_user(chat_id, "waiting", "voice"); send_msg(chat_id, "🎙 Текст:"); return
    if text == "📝 Суммаризация":
        set_user(chat_id, "waiting", "summarize"); send_msg(chat_id, "📝 Текст:"); return
    if text == "🇬🇧→🇷🇺 Перевод EN-RU":
        set_user(chat_id, "waiting", "enru"); send_msg(chat_id, "🇬🇧→🇷🇺 Текст:"); return
    if text == "🇷🇺→🇬🇧 Перевод RU-EN":
        set_user(chat_id, "waiting", "ruen"); send_msg(chat_id, "🇷🇺→🇬🇧 Текст:"); return
    if text == "🗑 Очистить контекст":
        set_user(chat_id, "context", [])
        send_msg(chat_id, "🗑 Очищено!", reply_kb=main_reply_kb())
        return

    if text == "📌 Избранное":
        favs = get_favorites(chat_id)
        if favs:
            msg = "📌 Избранное:\n\n"
            for i, f in enumerate(favs[-10:], 1):
                msg += f"{i}. [{f['date']}]\n{f['text'][:200]}\n\n"
            send_msg(chat_id, msg)
        else:
            send_msg(chat_id, "📌 Пусто.")
        return

    if text == "📝 Заметки":
        notes = get_notes(chat_id)
        if notes:
            msg = "📝 Заметки:\n\n"
            for i, n in enumerate(notes[-10:], 1):
                msg += f"{i}. [{n['date']}]\n{n['text'][:200]}\n\n"
            send_msg(chat_id, msg)
        else:
            send_msg(chat_id, "📝 Пусто. /note текст")
        return

    if text == "🔄 Подробнее":
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Подробнее.", get_context(chat_id))
        add_context(chat_id, "user", "Подробнее")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())
        return

    if text == "✏️ Переписать":
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Перепиши лучше.", get_context(chat_id))
        add_context(chat_id, "user", "Переписать")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())
        return

    if text == "📋 Список":
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Оформи списком.", get_context(chat_id))
        add_context(chat_id, "user", "Списком")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())
        return

    if text == "🎯 Пример":
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Пример с цифрами.", get_context(chat_id))
        add_context(chat_id, "user", "Пример")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())
        return

    if text == "🖼 Нарисовать":
        send_typing(chat_id)
        prompt = call_ai("Отвечай ТОЛЬКО промтом.", "Короткий промт на английском для картинки. 10 слов макс.",
                         get_context(chat_id))
        prompt = prompt.strip().strip('"').strip("'").strip("`")[:200]
        send_msg(chat_id, f"🎨 {prompt}\n⏳ Подожди...")
        img_path = generate_image(prompt)
        send_photo(chat_id, img_path, "🖼 " + prompt)
        return

    if text == "🎙 Озвучить":
        send_typing(chat_id)
        ctx = get_context(chat_id)
        if not ctx:
            send_msg(chat_id, "❌ Нечего озвучивать."); return
        send_msg(chat_id, "🎙 Создаю...")
        voice_path = create_voice(ctx[-1]["text"][:500])
        if voice_path:
            send_voice(chat_id, voice_path)
        else:
            send_msg(chat_id, "❌ Ошибка озвучки.")
        return

    if text == "📌 В избранное":
        ctx = get_context(chat_id)
        if ctx:
            add_favorite(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📌 Добавлено!")
        else:
            send_msg(chat_id, "❌ Пусто.")
        return

    if text == "📝 В заметки":
        ctx = get_context(chat_id)
        if ctx:
            add_note(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📝 Сохранено!")
        else:
            send_msg(chat_id, "❌ Пусто.")
        return

    # === WAITING STATES ===
    waiting = get_user(chat_id, "waiting", "")

    if waiting == "search":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        update_stats(chat_id)
        results = search_web(text)
        answer = call_ai(get_mode_prompt(chat_id),
                         "Поиск '" + text + "':\n\n" + results + "\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Поиск: " + text)
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🔍 " + text + "\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if waiting == "parse":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        update_stats(chat_id)
        content = parse_website(text)
        answer = call_ai(get_mode_prompt(chat_id),
                         "Сайт " + text + ":\n\n" + content + "\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Парсинг: " + text)
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🌐\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if waiting == "image":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        send_msg(chat_id, f"🎨 {text}\n⏳ Подожди...")
        img_path = generate_image(text)
        send_photo(chat_id, img_path, "🖼 " + text[:200])
        return

    if waiting == "voice":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        send_msg(chat_id, "🎙 Создаю...")
        voice_path = create_voice(text[:500])
        if voice_path:
            send_voice(chat_id, voice_path)
        else:
            send_msg(chat_id, "❌ Ошибка озвучки.")
        return

    if waiting == "summarize":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        update_stats(chat_id)
        answer = call_ai("Суммаризатор.", "5 мыслей:\n\n" + text[:3000], [])
        add_context(chat_id, "user", "Суммаризация")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "📝\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if waiting == "enru":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        answer = call_ai("Переводчик.", "На русский:\n\n" + text, [])
        send_msg(chat_id, "🇬🇧→🇷🇺\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if waiting == "ruen":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        answer = call_ai("Переводчик.", "На английский:\n\n" + text, [])
        send_msg(chat_id, "🇷🇺→🇬🇧\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if waiting == "newnote":
        set_user(chat_id, "waiting", "")
        add_note(chat_id, text)
        send_msg(chat_id, "📝 Сохранено!")
        return

    # === DEFAULT: AI CHAT ===
    send_typing(chat_id)
    update_stats(chat_id)
    answer = call_ai(get_mode_prompt(chat_id), text, get_context(chat_id))
    add_context(chat_id, "user", text)
    add_context(chat_id, "assistant", answer)
    add_xp(25, f"Чат: {text[:50]}")
    send_msg(chat_id, answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())


# ============================================================
# FLASK ROUTES — TELEGRAM WEBHOOK
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if "callback_query" in data:
        try:
            handle_callback(data["callback_query"])
        except Exception as e:
            print("CB error:", e)
        return "ok"
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    if chat_id and text:
        try:
            handle_message(chat_id, text)
        except Exception as e:
            print("Msg error:", e)
            send_msg(chat_id, "Ошибка.")
    return "ok"


@app.route("/", methods=["GET"])
def home():
    return "Jarvis 2.0 is running!"


# ============================================================
# WEB API — ЧАТ, ПРОЕКТЫ, КВЕСТЫ, ГЕЙМИФИКАЦИЯ
# ============================================================

web_sessions = {}


def get_web_session(sid):
    if sid not in web_sessions:
        web_sessions[sid] = {"mode": "helper", "context": []}
    return web_sessions[sid]


@app.route("/chat")
def web_chat():
    return render_template("index.html")


@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json()
    sid = data.get("session_id", "")
    text = data.get("text", "").strip()
    if not sid or not text:
        return json.dumps({"error": "empty"}), 400, {"Content-Type": "application/json"}

    session = get_web_session(sid)
    mode = session["mode"]
    prompt = MODES.get(mode, MODES["helper"])["prompt"]

    session["context"].append({"role": "user", "text": text[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    answer = call_ai(prompt, text, session["context"])

    session["context"].append({"role": "assistant", "text": answer[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    add_xp(25, f"Web: {text[:50]}")

    return json.dumps({"answer": answer, "time": time.strftime("%H:%M")}, ensure_ascii=False), 200, {
        "Content-Type": "application/json"}


@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.get_json()
    sid = data.get("session_id", "")
    mode = data.get("mode", "helper")
    if sid and mode in MODES:
        session = get_web_session(sid)
        session["mode"] = mode
        session["context"] = []
        return json.dumps({"ok": True, "mode": MODES[mode]}, ensure_ascii=False), 200, {
            "Content-Type": "application/json"}
    return json.dumps({"error": "invalid"}), 400, {"Content-Type": "application/json"}


@app.route("/api/clear", methods=["POST"])
def api_clear():
    data = request.get_json()
    sid = data.get("session_id", "")
    if sid and sid in web_sessions:
        web_sessions[sid] = {"mode": "helper", "context": []}
    return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}


# === ПРОЕКТЫ ===

@app.route("/api/projects", methods=["GET"])
def get_projects():
    data = read_json("projects.json", {"projects": []})
    return json.dumps(data, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    new_project = {
        "id": str(int(time.time() * 1000)),
        "name": req.get("name", "Без названия"),
        "description": req.get("description", ""),
        "monetization": req.get("monetization", ""),
        "status": "active",
        "sprint": 1,
        "revenue": 0,
        "created_at": datetime.now().isoformat()
    }
    data["projects"].append(new_project)
    write_json("projects.json", data)
    add_xp(100, f"Новый проект: {new_project['name']}")
    return json.dumps(new_project, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            data["projects"][i].update(req)
            write_json("projects.json", data)
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    data = read_json("projects.json", {"projects": []})
    data["projects"] = [p for p in data["projects"] if p["id"] != project_id]
    write_json("projects.json", data)
    return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}


# === КВЕСТЫ ===

@app.route("/api/quests", methods=["GET"])
def get_quests():
    return json.dumps(read_json("quests.json", {"quests": []}), ensure_ascii=False), 200, {
        "Content-Type": "application/json"}


@app.route("/api/quests", methods=["POST"])
def create_quest():
    data = read_json("quests.json", {"quests": []})
    req = request.get_json()
    quest = {
        "id": str(int(time.time() * 1000)),
        "name": req.get("name", ""),
        "priority": req.get("priority", "normal"),
        "xp_reward": req.get("xp_reward", 100),
        "tasks": req.get("tasks", []),
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    data["quests"].append(quest)
    write_json("quests.json", data)
    return json.dumps(quest, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/quests/<quest_id>", methods=["PUT"])
def update_quest(quest_id):
    data = read_json("quests.json", {"quests": []})
    req = request.get_json()
    for i, q in enumerate(data["quests"]):
        if q["id"] == quest_id:
            data["quests"][i].update(req)
            if req.get("completed"):
                add_xp(q.get("xp_reward", 100), f"Квест: {q['name']}")
            write_json("quests.json", data)
            return json.dumps(data["quests"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ИГРОК ===

@app.route("/api/player", methods=["GET"])
def get_player_route():
    return json.dumps(get_player(), ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/player/add-xp", methods=["POST"])
def add_xp_route():
    req = request.get_json()
    amount = req.get("amount", 0)
    reason = req.get("reason", "")
    player, leveled = add_xp(amount, reason)
    return json.dumps({"player": player, "leveled": leveled}, ensure_ascii=False), 200, {
        "Content-Type": "application/json"}


# === АНАЛИЗ НИШИ ===

@app.route("/api/analyze-niche", methods=["POST"])
def analyze_niche():
    try:
        req = request.get_json()
        niche = req.get("niche", "")
        description = req.get("description", "")

        prompt = f"""Проанализируй бизнес-нишу и дай структурированную оценку.

Ниша: {niche}
Описание: {description or 'Нет описания'}

Дай оценку в формате БИЗНЕС-ОЦЕНКИ.
Также добавь:
- 3 главных риска
- 3 конкурента
- Стратегию входа
- План на 4 недели (4 спринта)"""

        answer = call_ai(JARVIS_SYSTEM_PROMPT, prompt, [])
        add_xp(50, f"Анализ ниши: {niche}")

        return json.dumps({"analysis": answer, "timestamp": datetime.now().isoformat()},
                          ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === ГЕНЕРАЦИЯ СПРИНТОВ ===

@app.route("/api/generate-sprints", methods=["POST"])
def generate_sprints():
    try:
        req = request.get_json()
        project = req.get("project", "")
        weeks = req.get("weeks", 4)

        prompt = f"""Разбей проект на {weeks} недельных спринтов.

Проект: {project}

Для каждого спринта:
1. Цель (одно предложение)
2. 4-6 задач (чек-лист)
3. Критерий готовности
4. Ожидаемый результат"""

        answer = call_ai(JARVIS_SYSTEM_PROMPT, prompt, [])

        return json.dumps({"sprints": answer, "timestamp": datetime.now().isoformat()},
                          ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === СТАТИСТИКА ===

@app.route("/api/stats", methods=["GET"])
def get_stats_route():
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    player = get_player()

    active = [p for p in projects["projects"] if p.get("status") == "active"]
    total_rev = sum(p.get("revenue", 0) for p in projects["projects"])

    return json.dumps({
        "active_projects": len(active),
        "total_projects": len(projects["projects"]),
        "total_revenue": total_rev,
        "active_quests": len([q for q in quests["quests"] if not q.get("completed")]),
        "completed_quests": len([q for q in quests["quests"] if q.get("completed")]),
        "player": player
    }, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/modes", methods=["GET"])
def api_modes():
    return json.dumps(MODES, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# ============================================================
# ЗАПУСК
# ============================================================

def setup_webhook():
    if RENDER_URL and TELEGRAM_BOT_TOKEN:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/setWebhook"
        try:
            resp = requests.post(url, json={"url": RENDER_URL + "/webhook"}, timeout=10)
            print("Webhook:", resp.json())
        except Exception as e:
            print("Webhook error:", e)


def keep_alive():
    while True:
        time.sleep(600)
        if RENDER_URL:
            try:
                requests.get(RENDER_URL, timeout=10)
            except:
                pass


if __name__ == "__main__":
    setup_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"\n🤖 JARVIS 2.0 запущен на http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port)
