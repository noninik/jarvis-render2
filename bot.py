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
from datetime import datetime, date, timedelta
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
RENDER_URL = os.getenv("RENDER_URL", "")

app = Flask(__name__)
user_data = {}

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


# ============================================================
# РЕЖИМЫ AI
# ============================================================

MODES = {
    "helper": {"name": "💬 Помощник", "prompt": "Ты универсальный AI-помощник Jarvis. Отвечай кратко и по делу на русском.", "emoji": "💬"},
    "business": {"name": "📊 Бизнес-аналитик", "prompt": "Ты бизнес-аналитик Jarvis. Анализируй рынки, конкурентов, тренды. На русском.", "emoji": "📊"},
    "content": {"name": "✍️ Контент-менеджер", "prompt": "Ты контент-менеджер Jarvis. Пишешь посты, статьи, рекламу. На русском.", "emoji": "✍️"},
    "coder": {"name": "💻 Программист", "prompt": "Ты full-stack разработчик Jarvis. Пишешь чистый код. На русском.", "emoji": "💻"},
    "startup": {"name": "📋 Стартап-консультант", "prompt": "Ты стартап-консультант Jarvis. Бизнес-планы, идеи. На русском.", "emoji": "📋"},
    "research": {"name": "🔍 Исследователь", "prompt": "Ты исследователь рынка Jarvis. Анализируй ниши, тренды. На русском.", "emoji": "🔍"},
    "automate": {"name": "🚀 Автоматизатор", "prompt": "Ты эксперт по автоматизации Jarvis. Скрипты, боты. На русском.", "emoji": "🚀"},
    "copywriter": {"name": "📝 Копирайтер", "prompt": "Ты копирайтер Jarvis. Продающие тексты. На русском.", "emoji": "📝"},
    "coach": {"name": "🎯 Коуч", "prompt": "Ты лайф-коуч Jarvis. Цели, мотивация. На русском.", "emoji": "🎯"},
    "translator": {"name": "🌍 Переводчик", "prompt": "Ты переводчик Jarvis. Переводишь тексты. На русском.", "emoji": "🌍"},
}

DEFAULT_MODE = "helper"

JARVIS_SYSTEM_PROMPT = """Ты — JARVIS 2.0, продвинутый командный центр для серийного предпринимателя.
Отвечай конкретно, без воды, на русском. Используй эмодзи умеренно.

ФОРМАТ БИЗНЕС-ОЦЕНКИ:
📊 Ниша: [название]
🎯 ЦА: [кто]
💰 Монетизация: [как]
⚡ Конкуренция: [низкая/средняя/высокая]
🕐 MVP: [сколько]
📈 TAM: [оценка]
✅ Вердикт: [стоит/нет + почему]"""


# ============================================================
# ШАБЛОНЫ
# ============================================================

TEMPLATES = {
    "biz_plan": {"name": "📋 Бизнес-план", "prompt": "Создай детальный бизнес-план. Спроси нишу и бюджет, потом создай план: идея, ЦА, конкуренты, MVP, монетизация, маркетинг, финансы, риски."},
    "content_plan": {"name": "📅 Контент-план", "prompt": "Создай контент-план на 2 недели. Спроси нишу, дай план: дата, тема, формат, хештеги."},
    "competitor": {"name": "🔍 Анализ конкурентов", "prompt": "Проведи анализ конкурентов. Спроси нишу, проанализируй 5 конкурентов."},
    "resume": {"name": "📄 Резюме", "prompt": "Помоги составить резюме. Спроси должность и опыт."},
    "post_pack": {"name": "✍️ Пак постов", "prompt": "Создай 10 постов для соцсетей. Спроси нишу и тон."},
    "landing": {"name": "🌐 Текст лендинга", "prompt": "Напиши текст лендинга. Спроси продукт."},
    "email_chain": {"name": "📧 Email-цепочка", "prompt": "Создай 5 писем для прогрева клиента."},
    "swot": {"name": "📊 SWOT-анализ", "prompt": "Проведи SWOT-анализ. Спроси бизнес."},
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
# ВОРОНКА ГИПОТЕЗ
# ============================================================

FUNNEL_STAGES = ["idea", "validation", "mvp", "launch", "growth"]
FUNNEL_NAMES = {
    "idea": "💡 Идея",
    "validation": "🔍 Валидация",
    "mvp": "🛠 MVP",
    "launch": "🚀 Запуск",
    "growth": "📈 Рост"
}
FUNNEL_XP = {
    "idea": 0,
    "validation": 200,
    "mvp": 400,
    "launch": 600,
    "growth": 1000
}


# ============================================================
# ДОСТИЖЕНИЯ
# ============================================================

ACHIEVEMENTS = {
    "first_chat": {"name": "Первый чат", "icon": "💬", "desc": "Отправь первое сообщение", "check": lambda p, s: s.get("total_messages", 0) >= 1},
    "first_project": {"name": "Первый проект", "icon": "🚀", "desc": "Создай первый проект", "check": lambda p, s: s.get("total_projects", 0) >= 1},
    "five_projects": {"name": "5 проектов", "icon": "📦", "desc": "Создай 5 проектов", "check": lambda p, s: s.get("total_projects", 0) >= 5},
    "ten_projects": {"name": "10 проектов", "icon": "🏭", "desc": "Создай 10 проектов", "check": lambda p, s: s.get("total_projects", 0) >= 10},
    "first_quest": {"name": "Первый квест", "icon": "⚔️", "desc": "Заверши первый квест", "check": lambda p, s: s.get("completed_quests", 0) >= 1},
    "ten_quests": {"name": "10 квестов", "icon": "🗡️", "desc": "Заверши 10 квестов", "check": lambda p, s: s.get("completed_quests", 0) >= 10},
    "xp_100": {"name": "100 XP", "icon": "⚡", "desc": "Набери 100 XP", "check": lambda p, s: p.get("total_xp", 0) >= 100},
    "xp_1000": {"name": "1000 XP", "icon": "🔥", "desc": "Набери 1000 XP", "check": lambda p, s: p.get("total_xp", 0) >= 1000},
    "xp_5000": {"name": "5000 XP", "icon": "💎", "desc": "Набери 5000 XP", "check": lambda p, s: p.get("total_xp", 0) >= 5000},
    "xp_10000": {"name": "10000 XP", "icon": "👑", "desc": "Набери 10000 XP", "check": lambda p, s: p.get("total_xp", 0) >= 10000},
    "streak_3": {"name": "3 дня подряд", "icon": "🔥", "desc": "Будь активен 3 дня подряд", "check": lambda p, s: p.get("streak", 0) >= 3},
    "streak_7": {"name": "Неделя огня", "icon": "🔥🔥", "desc": "7 дней подряд", "check": lambda p, s: p.get("streak", 0) >= 7},
    "streak_30": {"name": "Месяц огня", "icon": "🔥🔥🔥", "desc": "30 дней подряд", "check": lambda p, s: p.get("streak", 0) >= 30},
    "first_revenue": {"name": "Первый $", "icon": "💰", "desc": "Заработай первый доллар", "check": lambda p, s: s.get("total_revenue", 0) > 0},
    "revenue_1k": {"name": "$1K MRR", "icon": "💰💰", "desc": "Достигни $1000 дохода", "check": lambda p, s: s.get("total_revenue", 0) >= 1000},
    "revenue_10k": {"name": "$10K MRR", "icon": "💰💰💰", "desc": "Достигни $10000 дохода", "check": lambda p, s: s.get("total_revenue", 0) >= 10000},
    "niche_analyst": {"name": "Аналитик", "icon": "🔍", "desc": "Проанализируй 5 ниш", "check": lambda p, s: s.get("niches_analyzed", 0) >= 5},
    "niche_expert": {"name": "Эксперт ниш", "icon": "🔬", "desc": "Проанализируй 20 ниш", "check": lambda p, s: s.get("niches_analyzed", 0) >= 20},
    "level_5": {"name": "Уровень 5", "icon": "⭐", "desc": "Достигни 5 уровня", "check": lambda p, s: p.get("level", 1) >= 5},
    "level_10": {"name": "Уровень 10", "icon": "🌟", "desc": "Достигни 10 уровня", "check": lambda p, s: p.get("level", 1) >= 10},
    "level_20": {"name": "Уровень 20", "icon": "✨", "desc": "Достигни 20 уровня", "check": lambda p, s: p.get("level", 1) >= 20},
    "first_mvp": {"name": "Первый MVP", "icon": "🛠", "desc": "Доведи проект до стадии MVP", "check": lambda p, s: s.get("mvp_count", 0) >= 1},
    "first_launch": {"name": "Первый запуск", "icon": "🚀", "desc": "Запусти проект", "check": lambda p, s: s.get("launch_count", 0) >= 1},
}


# ============================================================
# JSON УТИЛИТЫ
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
# ГЕЙМИФИКАЦИЯ — XP, УРОВНИ, STREAK, ДОСТИЖЕНИЯ
# ============================================================

def get_player():
    return read_json("player.json", {
        "level": 1,
        "xp": 0,
        "xp_to_next": 1000,
        "total_xp": 0,
        "rank": "Новичок",
        "streak": 0,
        "max_streak": 0,
        "last_active": "",
        "unlocked": []
    })


def update_streak(player):
    """Корректный подсчёт streak"""
    today = date.today().isoformat()
    last = player.get("last_active", "")

    if last == today:
        return  # уже обновляли сегодня

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    if last == yesterday:
        player["streak"] = player.get("streak", 0) + 1
    else:
        player["streak"] = 1

    # Обновляем максимальный streak
    if player["streak"] > player.get("max_streak", 0):
        player["max_streak"] = player["streak"]

    player["last_active"] = today


def add_xp(amount, reason=""):
    ranks = ["Новичок", "Стажёр", "Предприниматель", "Бизнесмен",
             "Стратег", "Магнат", "Титан", "Легенда"]

    player = get_player()
    player["xp"] += amount
    player["total_xp"] = player.get("total_xp", 0) + amount

    leveled = False
    while player["xp"] >= player["xp_to_next"]:
        player["xp"] -= player["xp_to_next"]
        player["level"] += 1
        player["xp_to_next"] = int(player["xp_to_next"] * 1.3)
        rank_idx = min(player["level"] // 5, len(ranks) - 1)
        player["rank"] = ranks[rank_idx]
        leveled = True

    # Streak
    update_streak(player)

    # Достижения
    stats = get_global_stats()
    unlocked = player.get("unlocked", [])
    new_achievements = []
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id not in unlocked:
            try:
                if ach["check"](player, stats):
                    unlocked.append(ach_id)
                    new_achievements.append(ach)
            except:
                pass
    player["unlocked"] = unlocked

    write_json("player.json", player)

    # Сохраняем снимок для графиков
    save_daily_snapshot()

    return player, leveled, new_achievements


def get_global_stats():
    """Собирает глобальную статистику для проверки достижений"""
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})

    project_list = projects.get("projects", [])
    active_projects = [p for p in project_list if p.get("status") != "archived"]

    return {
        "total_projects": len(project_list),
        "active_projects": len(active_projects),
        "total_revenue": sum(p.get("revenue", 0) for p in project_list),
        "completed_quests": len([q for q in quests.get("quests", []) if q.get("completed")]),
        "total_messages": activity.get("total_messages", 0),
        "niches_analyzed": activity.get("niches_analyzed", 0),
        "mvp_count": len([p for p in project_list if p.get("stage") in ["mvp", "launch", "growth"]]),
        "launch_count": len([p for p in project_list if p.get("stage") in ["launch", "growth"]]),
    }


def track_activity(action):
    """Трекает активность для достижений"""
    activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})
    if action == "message":
        activity["total_messages"] = activity.get("total_messages", 0) + 1
    elif action == "niche":
        activity["niches_analyzed"] = activity.get("niches_analyzed", 0) + 1
    write_json("activity.json", activity)


def save_daily_snapshot():
    """Сохраняет ежедневный снимок для графиков"""
    history = read_json("history.json", {"entries": []})
    stats = get_global_stats()
    player = read_json("player.json", {})

    today = date.today().isoformat()
    entry = {
        "date": today,
        "xp": player.get("total_xp", 0),
        "level": player.get("level", 1),
        "revenue": stats.get("total_revenue", 0),
        "projects": stats.get("total_projects", 0),
        "quests": stats.get("completed_quests", 0),
        "streak": player.get("streak", 0),
        "messages": stats.get("total_messages", 0)
    }

    # Обновляем или добавляем
    if history["entries"] and history["entries"][-1].get("date") == today:
        history["entries"][-1] = entry
    else:
        history["entries"].append(entry)

    # Максимум 90 дней
    history["entries"] = history["entries"][-90:]
    write_json("history.json", history)


# ============================================================
# WEEKLY MISSION
# ============================================================

def get_weekly_mission():
    mission = read_json("mission.json", {})
    today = date.today()
    if not mission or not mission.get("week_start"):
        mission = generate_weekly_mission()
    else:
        try:
            start = date.fromisoformat(mission["week_start"])
            if (today - start).days >= 7:
                mission = generate_weekly_mission()
        except:
            mission = generate_weekly_mission()
    return mission


def generate_weekly_mission():
    projects = read_json("projects.json", {"projects": []})
    player = get_player()
    active = [p for p in projects.get("projects", []) if p.get("status") == "active"]

    if not active:
        mission_name = "Создай первый проект"
        tasks = [
            {"text": "Придумай идею для бизнеса", "done": False},
            {"text": "Создай проект в JARVIS", "done": False},
            {"text": "Проанализируй нишу", "done": False},
            {"text": "Напиши описание продукта", "done": False},
        ]
    elif player.get("level", 1) < 3:
        mission_name = "Запусти MVP"
        tasks = [
            {"text": "Определи ЦА", "done": False},
            {"text": "Создай лендинг", "done": False},
            {"text": "Настрой аналитику", "done": False},
            {"text": "Получи первый отклик", "done": False},
        ]
    elif player.get("level", 1) < 7:
        mission_name = "Масштабируй бизнес"
        tasks = [
            {"text": "Проанализируй 3 новых ниши", "done": False},
            {"text": "Запусти A/B тест", "done": False},
            {"text": "Найди партнёра", "done": False},
            {"text": "Увеличь конверсию на 10%", "done": False},
        ]
    else:
        mission_name = "Выйди на новый уровень"
        tasks = [
            {"text": "Запусти новый продукт", "done": False},
            {"text": "Автоматизируй процесс", "done": False},
            {"text": "Делегируй 3 задачи", "done": False},
            {"text": "Достигни $1K MRR", "done": False},
        ]

    today = date.today()
    end = today + timedelta(days=(6 - today.weekday()))

    mission = {
        "name": mission_name,
        "tasks": tasks,
        "xp_reward": 500,
        "week_start": today.isoformat(),
        "week_end": end.isoformat(),
    }

    write_json("mission.json", mission)
    return mission


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
            if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
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
                    timeout=30, capture_output=True)
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
# AI ВЫЗОВ
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
# АВТОГЕНЕРАЦИЯ КВЕСТОВ ПРИ СОЗДАНИИ ПРОЕКТА
# ============================================================

def auto_generate_quests(project):
    """Генерирует квесты для нового проекта через AI"""
    prompt = f"""Создай 3 квеста (задания) для проекта.

Проект: {project['name']}
Описание: {project.get('description', '')}
Монетизация: {project.get('monetization', '')}

Ответь СТРОГО в JSON формате, без лишнего текста:
[
  {{"name": "название квеста", "priority": "urgent", "tasks": ["задача 1", "задача 2", "задача 3"]}},
  {{"name": "название квеста", "priority": "normal", "tasks": ["задача 1", "задача 2", "задача 3"]}},
  {{"name": "название квеста", "priority": "normal", "tasks": ["задача 1", "задача 2", "задача 3"]}}
]

Первый квест — срочный (валидация идеи).
Второй — создание MVP.
Третий — первые продажи."""

    answer = call_ai("Отвечай ТОЛЬКО JSON массивом. Без пояснений.", prompt, [])

    try:
        start = answer.find('[')
        end = answer.rfind(']') + 1
        if start >= 0 and end > start:
            quest_data = json.loads(answer[start:end])
        else:
            return []

        quests_file = read_json("quests.json", {"quests": []})
        created = []
        for q in quest_data:
            tasks = [{"text": t, "done": False} for t in q.get("tasks", [])]
            quest = {
                "id": str(int(time.time() * 1000)) + str(len(created)),
                "name": q.get("name", "Квест"),
                "priority": q.get("priority", "normal"),
                "xp_reward": 250 if q.get("priority") == "urgent" else 150,
                "tasks": tasks,
                "completed": False,
                "project_id": project["id"],
                "created_at": datetime.now().isoformat()
            }
            quests_file["quests"].append(quest)
            created.append(quest)

        write_json("quests.json", quests_file)
        return created
    except:
        return []


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
            json={"chat_id": chat_id, "text": "⌨️", "reply_markup": reply_kb}, timeout=30)
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
                requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto",
                              data={"chat_id": chat_id, "caption": caption[:1000]},
                              files={"photo": ("image.jpg", f, "image/jpeg")}, timeout=60)
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
    except:
        send_msg(chat_id, "❌ Ошибка голосового.")
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
# TELEGRAM CALLBACK
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

    elif data == "tool_search":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "search"); send_msg(chat_id, "🔍 Напиши запрос:")
    elif data == "tool_parse":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "parse"); send_msg(chat_id, "🌐 Отправь ссылку:")
    elif data == "tool_image":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "image"); send_msg(chat_id, "🖼 Опиши что нарисовать:")
    elif data == "tool_voice":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "voice"); send_msg(chat_id, "🎙 Напиши текст:")
    elif data == "tool_summarize":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "summarize"); send_msg(chat_id, "📝 Отправь текст:")
    elif data == "tool_enru":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "enru"); send_msg(chat_id, "🇬🇧→🇷🇺 Текст:")
    elif data == "tool_ruen":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id)
        set_user(chat_id, "waiting", "ruen"); send_msg(chat_id, "🇷🇺→🇬🇧 Текст:")

    elif data == "tool_clear":
        answer_cb(cb_id, "Очищено!")
        set_user(chat_id, "context", [])
        edit_msg(chat_id, old_msg_id, "🗑 Очищено!", main_inline_kb())

    elif data == "act_more":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Подробнее. Больше деталей и примеров.", get_context(chat_id))
        add_context(chat_id, "user", "Подробнее"); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_rewrite":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Перепиши лучше.", get_context(chat_id))
        add_context(chat_id, "user", "Переписать"); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_list":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Оформи списком.", get_context(chat_id))
        add_context(chat_id, "user", "Списком"); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_example":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Пример с цифрами.", get_context(chat_id))
        add_context(chat_id, "user", "Пример"); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb())

    elif data == "act_image":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        prompt = call_ai("Отвечай ТОЛЬКО промтом.", "Короткий промт на английском для картинки. 10 слов макс.", get_context(chat_id))
        prompt = prompt.strip().strip('"\'`')[:200]
        send_msg(chat_id, f"🎨 {prompt}\n⏳ Подожди...")
        img_path = generate_image(prompt)
        send_photo(chat_id, img_path, "🖼 " + prompt)

    elif data == "act_voice":
        answer_cb(cb_id); delete_msg(chat_id, old_msg_id); send_typing(chat_id)
        ctx = get_context(chat_id)
        if not ctx:
            send_msg(chat_id, "❌ Нечего озвучивать."); return
        send_msg(chat_id, "🎙 Создаю...")
        voice_path = create_voice(ctx[-1]["text"][:500])
        if voice_path:
            send_voice(chat_id, voice_path)
        else:
            send_msg(chat_id, "❌ Ошибка озвучки.")

    elif data == "act_fav":
        answer_cb(cb_id, "📌 Добавлено!")
        ctx = get_context(chat_id)
        if ctx: add_favorite(chat_id, ctx[-1]["text"])

    elif data == "act_note":
        answer_cb(cb_id, "📝 Сохранено!")
        ctx = get_context(chat_id)
        if ctx: add_note(chat_id, ctx[-1]["text"])

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
            edit_msg(chat_id, old_msg_id, "📝 Пусто.", main_inline_kb())

    elif data == "back_main":
        answer_cb(cb_id)
        mode = get_user(chat_id, "mode", DEFAULT_MODE)
        edit_msg(chat_id, old_msg_id, "🤖 Jarvis 2.0 | " + MODES.get(mode, MODES[DEFAULT_MODE])["name"], main_inline_kb())


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def handle_message(chat_id, text):
    text = text.strip()

    if text in ["/start", "/menu", "🏠 Меню", "⬅️ Назад в меню"]:
        send_msg(chat_id, "🤖 Jarvis AI Agent 2.0\n\nВыбери режим или напиши вопрос:",
                 reply_kb=main_reply_kb(), inline_kb=main_inline_kb())
        return

    if text.startswith("/note "):
        add_note(chat_id, text[6:].strip())
        send_msg(chat_id, "📝 Сохранено!")
        return

    if text in ["/stats", "📊 Статистика"]:
        stats = get_stats(chat_id)
        player = get_player()
        msg = f"📊 Статистика:\n\n"
        msg += f"⚡ Уровень: {player['level']} ({player['rank']})\n"
        msg += f"✨ XP: {player['xp']}/{player['xp_to_next']}\n"
        msg += f"🔥 Streak: {player.get('streak', 0)} дней (макс: {player.get('max_streak', 0)})\n"
        msg += f"💬 Сообщений: {stats.get('messages', 0)}\n\n"
        msg += f"🏆 Достижения: {len(player.get('unlocked', []))}/{len(ACHIEVEMENTS)}\n"
        for ach_id in player.get("unlocked", []):
            if ach_id in ACHIEVEMENTS:
                msg += f"  {ACHIEVEMENTS[ach_id]['icon']} {ACHIEVEMENTS[ach_id]['name']}\n"
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
        send_typing(chat_id); update_stats(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), TEMPLATES[key]["prompt"], get_context(chat_id))
        add_context(chat_id, "user", TEMPLATES[key]["prompt"])
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    if text == "🛠 Инструменты":
        send_msg(chat_id, "🛠 Инструменты:", reply_kb=tools_reply_kb(), inline_kb=tools_inline_kb())
        return

    if text == "🔍 Поиск": set_user(chat_id, "waiting", "search"); send_msg(chat_id, "🔍 Запрос:"); return
    if text == "🌐 Парсинг сайта": set_user(chat_id, "waiting", "parse"); send_msg(chat_id, "🌐 Ссылка:"); return
    if text == "🖼 Генерация фото": set_user(chat_id, "waiting", "image"); send_msg(chat_id, "🖼 Опиши:"); return
    if text == "🎙 Озвучка текста": set_user(chat_id, "waiting", "voice"); send_msg(chat_id, "🎙 Текст:"); return
    if text == "📝 Суммаризация": set_user(chat_id, "waiting", "summarize"); send_msg(chat_id, "📝 Текст:"); return
    if text == "🇬🇧→🇷🇺 Перевод EN-RU": set_user(chat_id, "waiting", "enru"); send_msg(chat_id, "🇬🇧→🇷🇺 Текст:"); return
    if text == "🇷🇺→🇬🇧 Перевод RU-EN": set_user(chat_id, "waiting", "ruen"); send_msg(chat_id, "🇷🇺→🇬🇧 Текст:"); return

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
        else:
            msg = "📌 Пусто."
        send_msg(chat_id, msg); return

    if text == "📝 Заметки":
        notes = get_notes(chat_id)
        if notes:
            msg = "📝 Заметки:\n\n"
            for i, n in enumerate(notes[-10:], 1):
                msg += f"{i}. [{n['date']}]\n{n['text'][:200]}\n\n"
        else:
            msg = "📝 Пусто. /note текст"
        send_msg(chat_id, msg); return

    # Quick actions
    quick = {
        "🔄 Подробнее": "Подробнее. Больше деталей.",
        "✏️ Переписать": "Перепиши лучше.",
        "📋 Список": "Оформи списком.",
        "🎯 Пример": "Пример с цифрами.",
    }
    if text in quick:
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), quick[text], get_context(chat_id))
        add_context(chat_id, "user", text); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, inline_kb=after_inline_kb()); return

    if text == "🖼 Нарисовать":
        send_typing(chat_id)
        prompt = call_ai("Отвечай ТОЛЬКО промтом.", "Короткий промт на английском для картинки. 10 слов макс.", get_context(chat_id))
        prompt = prompt.strip().strip('"\'`')[:200]
        send_msg(chat_id, f"🎨 {prompt}\n⏳ Подожди...")
        send_photo(chat_id, generate_image(prompt), "🖼 " + prompt); return

    if text == "🎙 Озвучить":
        send_typing(chat_id)
        ctx = get_context(chat_id)
        if not ctx: send_msg(chat_id, "❌ Нечего озвучивать."); return
        send_msg(chat_id, "🎙 Создаю...")
        vp = create_voice(ctx[-1]["text"][:500])
        if vp: send_voice(chat_id, vp)
        else: send_msg(chat_id, "❌ Ошибка озвучки.")
        return

    if text == "📌 В избранное":
        ctx = get_context(chat_id)
        if ctx: add_favorite(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📌 Добавлено!")
        else: send_msg(chat_id, "❌ Пусто.")
        return

    if text == "📝 В заметки":
        ctx = get_context(chat_id)
        if ctx: add_note(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📝 Сохранено!")
        else: send_msg(chat_id, "❌ Пусто.")
        return

    # Waiting states
    waiting = get_user(chat_id, "waiting", "")

    if waiting == "search":
        set_user(chat_id, "waiting", ""); send_typing(chat_id); update_stats(chat_id)
        results = search_web(text)
        answer = call_ai(get_mode_prompt(chat_id), f"Поиск '{text}':\n\n{results}\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Поиск: " + text); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🔍 " + text + "\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return

    if waiting == "parse":
        set_user(chat_id, "waiting", ""); send_typing(chat_id); update_stats(chat_id)
        content = parse_website(text)
        answer = call_ai(get_mode_prompt(chat_id), f"Сайт {text}:\n\n{content}\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Парсинг: " + text); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🌐\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return

    if waiting == "image":
        set_user(chat_id, "waiting", ""); send_typing(chat_id)
        send_msg(chat_id, f"🎨 {text}\n⏳ Подожди...")
        send_photo(chat_id, generate_image(text), "🖼 " + text[:200]); return

    if waiting == "voice":
        set_user(chat_id, "waiting", ""); send_typing(chat_id)
        send_msg(chat_id, "🎙 Создаю...")
        vp = create_voice(text[:500])
        if vp: send_voice(chat_id, vp)
        else: send_msg(chat_id, "❌ Ошибка озвучки.")
        return

    if waiting == "summarize":
        set_user(chat_id, "waiting", ""); send_typing(chat_id); update_stats(chat_id)
        answer = call_ai("Суммаризатор.", "5 мыслей:\n\n" + text[:3000], [])
        add_context(chat_id, "user", "Суммаризация"); add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "📝\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return

    if waiting == "enru":
        set_user(chat_id, "waiting", ""); send_typing(chat_id)
        answer = call_ai("Переводчик.", "На русский:\n\n" + text, [])
        send_msg(chat_id, "🇬🇧→🇷🇺\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return

    if waiting == "ruen":
        set_user(chat_id, "waiting", ""); send_typing(chat_id)
        answer = call_ai("Переводчик.", "На английский:\n\n" + text, [])
        send_msg(chat_id, "🇷🇺→🇬🇧\n\n" + answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return

    # Default AI
    send_typing(chat_id); update_stats(chat_id)
    track_activity("message")
    answer = call_ai(get_mode_prompt(chat_id), text, get_context(chat_id))
    add_context(chat_id, "user", text); add_context(chat_id, "assistant", answer)
    add_xp(25, f"Чат: {text[:50]}")
    send_msg(chat_id, answer, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())


# ============================================================
# FLASK — TELEGRAM WEBHOOK
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
# WEB API — ЧАТ
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
    prompt = MODES.get(session["mode"], MODES["helper"])["prompt"]

    session["context"].append({"role": "user", "text": text[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    answer = call_ai(prompt, text, session["context"])

    session["context"].append({"role": "assistant", "text": answer[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    track_activity("message")
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


# ============================================================
# WEB API — ПРОЕКТЫ
# ============================================================

@app.route("/api/projects", methods=["GET"])
def get_projects():
    data = read_json("projects.json", {"projects": []})
    # Фильтр по статусу
    status = request.args.get("status", "")
    stage = request.args.get("stage", "")
    projects = data.get("projects", [])
    if status:
        projects = [p for p in projects if p.get("status") == status]
    if stage:
        projects = [p for p in projects if p.get("stage") == stage]
    return json.dumps({"projects": projects}, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/projects", methods=["POST"])
def create_project():
    req = request.get_json()
    data = read_json("projects.json", {"projects": []})
    new_project = {
        "id": str(int(time.time() * 1000)),
        "name": req.get("name", "Без названия"),
        "description": req.get("description", ""),
        "monetization": req.get("monetization", ""),
        "status": "active",
        "stage": "idea",
        "stage_history": [{"to": "idea", "date": datetime.now().isoformat()}],
        "sprint": 1,
        "revenue": 0,
        "links": [],
        "notes": [],
        "created_at": datetime.now().isoformat()
    }
    data["projects"].append(new_project)
    write_json("projects.json", data)
    add_xp(100, f"Новый проект: {new_project['name']}")

    # Автогенерация квестов
    threading.Thread(target=auto_generate_quests, args=(new_project,), daemon=True).start()

    return json.dumps(new_project, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/projects/<project_id>", methods=["GET"])
def get_project(project_id):
    data = read_json("projects.json", {"projects": []})
    for p in data["projects"]:
        if p["id"] == project_id:
            # Подтягиваем квесты проекта
            quests = read_json("quests.json", {"quests": []})
            project_quests = [q for q in quests["quests"] if q.get("project_id") == project_id]
            p["quests"] = project_quests
            return json.dumps(p, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


@app.route("/api/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            # Не перезаписываем критичные поля напрямую
            safe_fields = ["name", "description", "monetization", "status", "sprint"]
            for field in safe_fields:
                if field in req:
                    data["projects"][i][field] = req[field]
            write_json("projects.json", data)
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    data = read_json("projects.json", {"projects": []})
    # Архивируем вместо удаления
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            data["projects"][i]["status"] = "archived"
            data["projects"][i]["archived_at"] = datetime.now().isoformat()
            write_json("projects.json", data)
            return json.dumps({"ok": True, "archived": True}), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ВОССТАНОВИТЬ ПРОЕКТ ИЗ АРХИВА ===

@app.route("/api/projects/<project_id>/restore", methods=["POST"])
def restore_project(project_id):
    data = read_json("projects.json", {"projects": []})
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            data["projects"][i]["status"] = "active"
            data["projects"][i].pop("archived_at", None)
            write_json("projects.json", data)
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ВОРОНКА — СМЕНИТЬ СТАДИЮ ===

@app.route("/api/projects/<project_id>/stage", methods=["PUT"])
def update_project_stage(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    new_stage = req.get("stage", "idea")

    if new_stage not in FUNNEL_STAGES:
        return json.dumps({"error": "Invalid stage"}), 400, {"Content-Type": "application/json"}

    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            old_stage = p.get("stage", "idea")
            data["projects"][i]["stage"] = new_stage

            # История переходов
            history = data["projects"][i].get("stage_history", [])
            history.append({
                "from": old_stage,
                "to": new_stage,
                "date": datetime.now().isoformat()
            })
            data["projects"][i]["stage_history"] = history

            write_json("projects.json", data)

            # XP за продвижение вперёд
            old_idx = FUNNEL_STAGES.index(old_stage) if old_stage in FUNNEL_STAGES else 0
            new_idx = FUNNEL_STAGES.index(new_stage)
            if new_idx > old_idx:
                xp = FUNNEL_XP.get(new_stage, 0)
                add_xp(xp, f"Стадия: {FUNNEL_NAMES[new_stage]}")

            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}

    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ВОРОНКА — ОБЗОР ===

@app.route("/api/funnel", methods=["GET"])
def get_funnel():
    """Проекты сгруппированные по стадиям воронки"""
    data = read_json("projects.json", {"projects": []})
    funnel = {}
    for stage in FUNNEL_STAGES:
        funnel[stage] = {
            "name": FUNNEL_NAMES[stage],
            "projects": [p for p in data["projects"]
                         if p.get("stage", "idea") == stage
                         and p.get("status") != "archived"]
        }
    return json.dumps(funnel, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# === ДОБАВИТЬ ДОХОД ===

@app.route("/api/projects/<project_id>/revenue", methods=["POST"])
def add_revenue(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    amount = req.get("amount", 0)
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            data["projects"][i]["revenue"] = data["projects"][i].get("revenue", 0) + amount

            # История доходов
            rev_history = data["projects"][i].get("revenue_history", [])
            rev_history.append({
                "amount": amount,
                "date": datetime.now().isoformat(),
                "note": req.get("note", "")
            })
            data["projects"][i]["revenue_history"] = rev_history

            write_json("projects.json", data)
            add_xp(50, f"Доход +${amount}")
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ДОБАВИТЬ ССЫЛКУ К ПРОЕКТУ ===

@app.route("/api/projects/<project_id>/links", methods=["POST"])
def add_link(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            links = data["projects"][i].get("links", [])
            links.append({
                "id": str(int(time.time() * 1000)),
                "url": req.get("url", ""),
                "title": req.get("title", ""),
                "added": datetime.now().isoformat()
            })
            data["projects"][i]["links"] = links
            write_json("projects.json", data)
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === УДАЛИТЬ ССЫЛКУ ===

@app.route("/api/projects/<project_id>/links/<link_id>", methods=["DELETE"])
def delete_link(project_id, link_id):
    data = read_json("projects.json", {"projects": []})
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            links = data["projects"][i].get("links", [])
            data["projects"][i]["links"] = [l for l in links if l.get("id") != link_id]
            write_json("projects.json", data)
            return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# === ЗАМЕТКИ В ПРОЕКТЕ ===

@app.route("/api/projects/<project_id>/notes", methods=["POST"])
def add_project_note(project_id):
    data = read_json("projects.json", {"projects": []})
    req = request.get_json()
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            notes = data["projects"][i].get("notes", [])
            notes.append({
                "id": str(int(time.time() * 1000)),
                "text": req.get("text", ""),
                "added": datetime.now().isoformat()
            })
            data["projects"][i]["notes"] = notes
            write_json("projects.json", data)
            return json.dumps(data["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# ============================================================
# WEB API — КВЕСТЫ
# ============================================================

@app.route("/api/quests", methods=["GET"])
def get_quests():
    data = read_json("quests.json", {"quests": []})
    project_id = request.args.get("project_id", "")
    if project_id:
        data["quests"] = [q for q in data["quests"] if q.get("project_id") == project_id]
    return json.dumps(data, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/quests", methods=["POST"])
def create_quest():
    data = read_json("quests.json", {"quests": []})
    req = request.get_json()
    tasks = [{"text": t, "done": False} if isinstance(t, str) else t for t in req.get("tasks", [])]
    quest = {
        "id": str(int(time.time() * 1000)),
        "name": req.get("name", ""),
        "priority": req.get("priority", "normal"),
        "xp_reward": req.get("xp_reward", 100),
        "tasks": tasks,
        "completed": False,
        "project_id": req.get("project_id", ""),
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
            was_completed = q.get("completed", False)
            data["quests"][i].update(req)

            # XP при первом завершении
            if req.get("completed") and not was_completed:
                add_xp(q.get("xp_reward", 100), f"Квест: {q['name']}")
                data["quests"][i]["completed_at"] = datetime.now().isoformat()

            write_json("quests.json", data)
            return json.dumps(data["quests"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


@app.route("/api/quests/<quest_id>", methods=["DELETE"])
def delete_quest(quest_id):
    data = read_json("quests.json", {"quests": []})
    data["quests"] = [q for q in data["quests"] if q["id"] != quest_id]
    write_json("quests.json", data)
    return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}


# === ОТМЕТИТЬ ПОДЗАДАЧУ ===

@app.route("/api/quests/<quest_id>/toggle-task", methods=["POST"])
def toggle_quest_task(quest_id):
    data = read_json("quests.json", {"quests": []})
    req = request.get_json()
    task_idx = req.get("index", 0)

    for i, q in enumerate(data["quests"]):
        if q["id"] == quest_id:
            tasks = q.get("tasks", [])
            if 0 <= task_idx < len(tasks):
                tasks[task_idx]["done"] = not tasks[task_idx]["done"]
                data["quests"][i]["tasks"] = tasks

                # Автозавершение квеста если все задачи выполнены
                all_done = all(t.get("done", False) for t in tasks)
                if all_done and not q.get("completed"):
                    data["quests"][i]["completed"] = True
                    data["quests"][i]["completed_at"] = datetime.now().isoformat()
                    add_xp(q.get("xp_reward", 100), f"Квест: {q['name']}")

                write_json("quests.json", data)
                return json.dumps(data["quests"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
    return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}


# ============================================================
# WEB API — ИГРОК И ГЕЙМИФИКАЦИЯ
# ============================================================

@app.route("/api/player", methods=["GET"])
def get_player_route():
    return json.dumps(get_player(), ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/player/add-xp", methods=["POST"])
def add_xp_route():
    req = request.get_json()
    player, leveled, new_ach = add_xp(req.get("amount", 0), req.get("reason", ""))
    return json.dumps({
        "player": player,
        "leveled": leveled,
        "new_achievements": [{"name": a["name"], "icon": a["icon"]} for a in new_ach]
    }, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# === ДОСТИЖЕНИЯ ===

@app.route("/api/achievements", methods=["GET"])
def get_achievements():
    player = get_player()
    unlocked = player.get("unlocked", [])
    result = []
    for ach_id, ach in ACHIEVEMENTS.items():
        result.append({
            "id": ach_id,
            "name": ach["name"],
            "icon": ach["icon"],
            "desc": ach["desc"],
            "unlocked": ach_id in unlocked
        })
    return json.dumps(result, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# === МИССИЯ НЕДЕЛИ ===

@app.route("/api/mission", methods=["GET"])
def get_mission():
    return json.dumps(get_weekly_mission(), ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/mission/toggle", methods=["POST"])
def toggle_mission_task():
    req = request.get_json()
    idx = req.get("index", 0)
    mission = get_weekly_mission()
    if 0 <= idx < len(mission.get("tasks", [])):
        mission["tasks"][idx]["done"] = not mission["tasks"][idx]["done"]
        # Проверяем все ли выполнены
        all_done = all(t["done"] for t in mission["tasks"])
        if all_done:
            add_xp(mission.get("xp_reward", 500), "Миссия недели завершена!")
            mission["completed"] = True
        write_json("mission.json", mission)
    return json.dumps(mission, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# ============================================================
# WEB API — АНАЛИТИКА
# ============================================================

@app.route("/api/analyze-niche", methods=["POST"])
def analyze_niche():
    try:
        req = request.get_json()
        niche = req.get("niche", "")
        prompt = f"""Проанализируй бизнес-нишу:

Ниша: {niche}

Дай оценку:
📊 Ниша, 🎯 ЦА, 💰 Монетизация, ⚡ Конкуренция, 🕐 MVP, 📈 TAM, ✅ Вердикт
+ 3 риска, 3 конкурента, стратегия входа, план на 4 недели"""

        answer = call_ai(JARVIS_SYSTEM_PROMPT, prompt, [])
        track_activity("niche")
        add_xp(50, f"Анализ ниши: {niche}")

        return json.dumps({"analysis": answer}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/generate-sprints", methods=["POST"])
def generate_sprints():
    try:
        req = request.get_json()
        project = req.get("project", "")
        weeks = req.get("weeks", 4)
        prompt = f"""Разбей проект на {weeks} недельных спринтов.
Проект: {project}
Для каждого: цель, 4-6 задач, критерий готовности."""

        answer = call_ai(JARVIS_SYSTEM_PROMPT, prompt, [])
        return json.dumps({"sprints": answer}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/score-idea", methods=["POST"])
def score_idea():
    try:
        req = request.get_json()
        idea = req.get("idea", "")
        prompt = f"""Оцени бизнес-идею по 5 критериям (от 1 до 10):

Идея: {idea}

Ответь СТРОГО в JSON:
{{"market": 8, "competition": 6, "mvp_speed": 9, "monetization": 7, "scalability": 5, "total": 70, "verdict": "краткий вердикт"}}

market = размер рынка
competition = мало конкурентов = высокий балл
mvp_speed = скорость создания MVP
monetization = потенциал монетизации
scalability = масштабируемость
total = среднее * 10"""

        answer = call_ai("Отвечай ТОЛЬКО JSON. Без пояснений.", prompt, [])
        try:
            start = answer.find('{')
            end = answer.rfind('}') + 1
            score = json.loads(answer[start:end])
        except:
            score = {"total": 0, "verdict": answer}

        track_activity("niche")
        return json.dumps(score, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# ============================================================
# WEB API — REDDIT ПОИСК
# ============================================================

@app.route("/api/reddit-search", methods=["POST"])
def reddit_search():
    """Поиск болей на Reddit без API ключа"""
    try:
        req = request.get_json()
        query = req.get("query", "")

        url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query)}&sort=relevance&limit=10"
        resp = requests.get(url, headers={"User-Agent": "JarvisBot/2.0"}, timeout=10)

        if resp.status_code != 200:
            return json.dumps({"error": "Reddit недоступен", "status": resp.status_code}), 500, {
                "Content-Type": "application/json"}

        posts = []
        for post in resp.json().get("data", {}).get("children", []):
            d = post.get("data", {})
            posts.append({
                "title": d.get("title", ""),
                "subreddit": d.get("subreddit", ""),
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "text": (d.get("selftext", ""))[:300]
            })

        # AI анализ болей
        pain_prompt = f"""Проанализируй эти посты с Reddit и выдели:
1. Топ-5 болей/проблем людей
2. Что люди готовы покупать
3. 3 идеи для бизнеса на основе этих болей

Посты:
{json.dumps(posts[:5], ensure_ascii=False)[:3000]}"""

        analysis = call_ai(JARVIS_SYSTEM_PROMPT, pain_prompt, [])
        track_activity("niche")
        add_xp(30, f"Reddit: {query}")

        return json.dumps({
            "posts": posts,
            "analysis": analysis
        }, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# ============================================================
# WEB API — ИСТОРИЯ И ГРАФИКИ
# ============================================================

@app.route("/api/history", methods=["GET"])
def get_history():
    """История для графиков"""
    history = read_json("history.json", {"entries": []})
    return json.dumps(history, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# ============================================================
# WEB API — СТАТИСТИКА
# ============================================================

@app.route("/api/stats", methods=["GET"])
def get_stats_route():
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    player = get_player()
    activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})

    project_list = projects.get("projects", [])
    active = [p for p in project_list if p.get("status") == "active"]
    archived = [p for p in project_list if p.get("status") == "archived"]
    total_rev = sum(p.get("revenue", 0) for p in project_list)

    quest_list = quests.get("quests", [])
    active_quests = [q for q in quest_list if not q.get("completed")]
    completed_quests = [q for q in quest_list if q.get("completed")]

    # Воронка
    funnel_summary = {}
    for stage in FUNNEL_STAGES:
        count = len([p for p in active if p.get("stage", "idea") == stage])
        funnel_summary[stage] = {"name": FUNNEL_NAMES[stage], "count": count}

    return json.dumps({
        "active_projects": len(active),
        "total_projects": len(project_list),
        "archived_projects": len(archived),
        "total_revenue": total_rev,
        "active_quests": len(active_quests),
        "completed_quests": len(completed_quests),
        "total_quests": len(quest_list),
        "total_messages": activity.get("total_messages", 0),
        "niches_analyzed": activity.get("niches_analyzed", 0),
        "player": player,
        "funnel": funnel_summary
    }, ensure_ascii=False), 200, {"Content-Type": "application/json"}


@app.route("/api/modes", methods=["GET"])
def api_modes():
    return json.dumps(MODES, ensure_ascii=False), 200, {"Content-Type": "application/json"}


# ============================================================
# ЗАПУСК
# ============================================================

def setup_webhook():
    if RENDER_URL and TELEGRAM_BOT_TOKEN:
        try:
            resp = requests.post(
                "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/setWebhook",
                json={"url": RENDER_URL + "/webhook"}, timeout=10)
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
    print(f"\n🤖 JARVIS 2.0 — http://localhost:{port}")
    print(f"📊 Web UI — http://localhost:{port}/chat")
    print(f"📡 API — http://localhost:{port}/api/stats\n")
    app.run(host="0.0.0.0", port=port)
