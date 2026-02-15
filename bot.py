from flask import Flask, request
import os
import json
import requests
import threading
import time
import subprocess
import asyncio
import urllib.parse
import uuid
import random
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
FUNNEL_XP = {"idea": 0, "validation": 200, "mvp": 400, "launch": 600, "growth": 1000}
STAGE_DEADLINE_DAYS = {"idea": 7, "validation": 14, "mvp": 21, "launch": 14, "growth": 0}


# ============================================================
# ТЕГИ ПРОЕКТОВ
# ============================================================

DEFAULT_TAGS = ["SaaS", "E-commerce", "Контент", "Фриланс", "Агентство",
                "Инфопродукт", "Маркетплейс", "Автоматизация", "AI", "Другое"]


# ============================================================
# ЕЖЕДНЕВНЫЕ ЧЕЛЛЕНДЖИ
# ============================================================

DAILY_CHALLENGES = [
    {"text": "Проанализируй 1 нишу", "xp": 50, "action": "niche"},
    {"text": "Напиши оффер для проекта", "xp": 75, "action": "offer"},
    {"text": "Заверши 2 задачи в квесте", "xp": 60, "action": "tasks"},
    {"text": "Найди 3 боли на Reddit", "xp": 80, "action": "reddit"},
    {"text": "Добавь доход в проект", "xp": 50, "action": "revenue"},
    {"text": "Создай новый проект", "xp": 100, "action": "project"},
    {"text": "Продвинь проект на 1 стадию", "xp": 100, "action": "stage"},
    {"text": "Напиши 5 сообщений AI", "xp": 40, "action": "chat"},
    {"text": "Проанализируй тренд", "xp": 60, "action": "trend"},
    {"text": "Добавь заметку к проекту", "xp": 30, "action": "note"},
    {"text": "Создай контент-план", "xp": 70, "action": "template"},
    {"text": "Сделай SWOT-анализ", "xp": 70, "action": "template"},
    {"text": "Найди 2 конкурента", "xp": 60, "action": "competitor"},
    {"text": "Обнови описание проекта", "xp": 30, "action": "update"},
]


# ============================================================
# ДОСТИЖЕНИЯ
# ============================================================

ACHIEVEMENTS = {
    "first_chat": {"name": "Первый чат", "icon": "💬", "desc": "Отправь первое сообщение"},
    "chatter": {"name": "Болтун", "icon": "🗣", "desc": "Отправь 100 сообщений"},
    "first_project": {"name": "Первый проект", "icon": "🚀", "desc": "Создай первый проект"},
    "five_projects": {"name": "5 проектов", "icon": "📦", "desc": "Создай 5 проектов"},
    "ten_projects": {"name": "10 проектов", "icon": "🏭", "desc": "Создай 10 проектов"},
    "first_quest": {"name": "Первый квест", "icon": "⚔️", "desc": "Заверши первый квест"},
    "ten_quests": {"name": "10 квестов", "icon": "🗡️", "desc": "Заверши 10 квестов"},
    "quest_master": {"name": "Мастер квестов", "icon": "👑", "desc": "Заверши 50 квестов"},
    "xp_100": {"name": "100 XP", "icon": "⚡", "desc": "Набери 100 XP"},
    "xp_1000": {"name": "1000 XP", "icon": "🔥", "desc": "Набери 1000 XP"},
    "xp_5000": {"name": "5000 XP", "icon": "💎", "desc": "Набери 5000 XP"},
    "xp_10000": {"name": "10000 XP", "icon": "👑", "desc": "Набери 10000 XP"},
    "streak_3": {"name": "3 дня подряд", "icon": "🔥", "desc": "Будь активен 3 дня подряд"},
    "streak_7": {"name": "Неделя огня", "icon": "🔥🔥", "desc": "7 дней подряд"},
    "streak_30": {"name": "Месяц огня", "icon": "🔥🔥🔥", "desc": "30 дней подряд"},
    "first_revenue": {"name": "Первый $", "icon": "💰", "desc": "Заработай первый доллар"},
    "revenue_1k": {"name": "$1K MRR", "icon": "💰💰", "desc": "Достигни $1000 дохода"},
    "revenue_10k": {"name": "$10K MRR", "icon": "💰💰💰", "desc": "Достигни $10000 дохода"},
    "niche_analyst": {"name": "Аналитик", "icon": "🔍", "desc": "Проанализируй 5 ниш"},
    "niche_expert": {"name": "Эксперт ниш", "icon": "🔬", "desc": "Проанализируй 20 ниш"},
    "level_5": {"name": "Уровень 5", "icon": "⭐", "desc": "Достигни 5 уровня"},
    "level_10": {"name": "Уровень 10", "icon": "🌟", "desc": "Достигни 10 уровня"},
    "level_20": {"name": "Уровень 20", "icon": "✨", "desc": "Достигни 20 уровня"},
    "first_mvp": {"name": "Первый MVP", "icon": "🛠", "desc": "Доведи проект до стадии MVP"},
    "first_launch": {"name": "Первый запуск", "icon": "🚀", "desc": "Запусти проект"},
    "serial_launcher": {"name": "Серийный запуск", "icon": "🚀🚀", "desc": "Запусти 5 проектов"},
    "daily_3": {"name": "3 челленджа", "icon": "📅", "desc": "Выполни 3 ежедневных челленджа"},
    "daily_30": {"name": "30 челленджей", "icon": "📅📅", "desc": "Выполни 30 ежедневных челленджей"},
    "pain_hunter": {"name": "Охотник за болями", "icon": "🎯", "desc": "Сохрани 10 болей в базу"},
    "sprint_master": {"name": "Спринт-мастер", "icon": "🏃", "desc": "Заверши 5 спринтов"},
}


def check_achievement(ach_id, player, stats):
    checks = {
        "first_chat": stats.get("total_messages", 0) >= 1,
        "chatter": stats.get("total_messages", 0) >= 100,
        "first_project": stats.get("total_projects", 0) >= 1,
        "five_projects": stats.get("total_projects", 0) >= 5,
        "ten_projects": stats.get("total_projects", 0) >= 10,
        "first_quest": stats.get("completed_quests", 0) >= 1,
        "ten_quests": stats.get("completed_quests", 0) >= 10,
        "quest_master": stats.get("completed_quests", 0) >= 50,
        "xp_100": player.get("total_xp", 0) >= 100,
        "xp_1000": player.get("total_xp", 0) >= 1000,
        "xp_5000": player.get("total_xp", 0) >= 5000,
        "xp_10000": player.get("total_xp", 0) >= 10000,
        "streak_3": player.get("streak", 0) >= 3,
        "streak_7": player.get("streak", 0) >= 7,
        "streak_30": player.get("streak", 0) >= 30,
        "first_revenue": stats.get("total_revenue", 0) > 0,
        "revenue_1k": stats.get("total_revenue", 0) >= 1000,
        "revenue_10k": stats.get("total_revenue", 0) >= 10000,
        "niche_analyst": stats.get("niches_analyzed", 0) >= 5,
        "niche_expert": stats.get("niches_analyzed", 0) >= 20,
        "level_5": player.get("level", 1) >= 5,
        "level_10": player.get("level", 1) >= 10,
        "level_20": player.get("level", 1) >= 20,
        "first_mvp": stats.get("mvp_count", 0) >= 1,
        "first_launch": stats.get("launch_count", 0) >= 1,
        "serial_launcher": stats.get("launch_count", 0) >= 5,
        "daily_3": stats.get("daily_completed", 0) >= 3,
        "daily_30": stats.get("daily_completed", 0) >= 30,
        "pain_hunter": stats.get("saved_pains", 0) >= 10,
        "sprint_master": stats.get("completed_sprints", 0) >= 5,
    }
    return checks.get(ach_id, False)


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
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Write error {filename}: {e}")


# ============================================================
# ГЕЙМИФИКАЦИЯ
# ============================================================

def get_player():
    default = {
        "level": 1, "xp": 0, "xp_to_next": 1000, "total_xp": 0,
        "rank": "Новичок", "streak": 0, "max_streak": 0,
        "last_active": "", "unlocked": [],
        "daily_completed": 0, "completed_sprints": 0
    }
    player = read_json("player.json", default)
    for k, v in default.items():
        if k not in player:
            player[k] = v
    return player


def update_streak(player):
    today_str = date.today().isoformat()
    last = player.get("last_active", "")
    if last == today_str:
        return
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    if last == yesterday_str:
        player["streak"] = player.get("streak", 0) + 1
    else:
        player["streak"] = 1
    if player["streak"] > player.get("max_streak", 0):
        player["max_streak"] = player["streak"]
    player["last_active"] = today_str


def add_xp(amount, reason=""):
    ranks = ["Новичок", "Стажёр", "Предприниматель", "Бизнесмен",
             "Стратег", "Магнат", "Титан", "Легенда"]
    player = get_player()
    player["xp"] = player.get("xp", 0) + amount
    player["total_xp"] = player.get("total_xp", 0) + amount
    leveled = False
    while player["xp"] >= player.get("xp_to_next", 1000):
        player["xp"] -= player["xp_to_next"]
        player["level"] = player.get("level", 1) + 1
        player["xp_to_next"] = int(player["xp_to_next"] * 1.3)
        rank_idx = min(player["level"] // 5, len(ranks) - 1)
        player["rank"] = ranks[rank_idx]
        leveled = True
    update_streak(player)
    stats = get_global_stats()
    unlocked = player.get("unlocked", [])
    new_achievements = []
    for ach_id in ACHIEVEMENTS:
        if ach_id not in unlocked:
            try:
                if check_achievement(ach_id, player, stats):
                    unlocked.append(ach_id)
                    new_achievements.append(ACHIEVEMENTS[ach_id])
            except Exception:
                pass
    player["unlocked"] = unlocked
    write_json("player.json", player)
    try:
        save_daily_snapshot()
    except Exception:
        pass
    return player, leveled, new_achievements


def get_global_stats():
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})
    pains = read_json("pains.json", {"pains": []})
    player = read_json("player.json", {})
    sprints_data = read_json("sprints.json", {"sprints": []})
    project_list = projects.get("projects", [])
    return {
        "total_projects": len(project_list),
        "active_projects": len([p for p in project_list if p.get("status") != "archived"]),
        "total_revenue": sum(p.get("revenue", 0) for p in project_list),
        "completed_quests": len([q for q in quests.get("quests", []) if q.get("completed")]),
        "total_messages": activity.get("total_messages", 0),
        "niches_analyzed": activity.get("niches_analyzed", 0),
        "mvp_count": len([p for p in project_list if p.get("stage") in ["mvp", "launch", "growth"]]),
        "launch_count": len([p for p in project_list if p.get("stage") in ["launch", "growth"]]),
        "daily_completed": player.get("daily_completed", 0),
        "saved_pains": len(pains.get("pains", [])),
        "completed_sprints": len([s for s in sprints_data.get("sprints", []) if s.get("completed")]),
    }


def track_activity(action):
    activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})
    if action == "message":
        activity["total_messages"] = activity.get("total_messages", 0) + 1
    elif action == "niche":
        activity["niches_analyzed"] = activity.get("niches_analyzed", 0) + 1
    write_json("activity.json", activity)


def save_daily_snapshot():
    history = read_json("history.json", {"entries": []})
    stats = get_global_stats()
    player = read_json("player.json", {})
    today_str = date.today().isoformat()
    entry = {
        "date": today_str,
        "xp": player.get("total_xp", 0),
        "level": player.get("level", 1),
        "revenue": stats.get("total_revenue", 0),
        "projects": stats.get("total_projects", 0),
        "quests": stats.get("completed_quests", 0),
        "streak": player.get("streak", 0),
        "messages": stats.get("total_messages", 0)
    }
    entries = history.get("entries", [])
    if entries and entries[-1].get("date") == today_str:
        entries[-1] = entry
    else:
        entries.append(entry)
    history["entries"] = entries[-90:]
    write_json("history.json", history)


# ============================================================
# DAILY CHALLENGE
# ============================================================

def get_daily_challenge():
    daily = read_json("daily.json", {})
    today_str = date.today().isoformat()
    if daily.get("date") != today_str:
        challenges = random.sample(DAILY_CHALLENGES, min(3, len(DAILY_CHALLENGES)))
        daily = {
            "date": today_str,
            "challenges": [{"text": c["text"], "xp": c["xp"], "action": c["action"], "done": False} for c in challenges],
            "completed": False
        }
        write_json("daily.json", daily)
    return daily


def complete_daily_challenge(index):
    daily = get_daily_challenge()
    challenges = daily.get("challenges", [])
    if 0 <= index < len(challenges) and not challenges[index]["done"]:
        challenges[index]["done"] = True
        daily["challenges"] = challenges
        xp_reward = challenges[index].get("xp", 50)
        all_done = all(c["done"] for c in challenges)
        if all_done:
            daily["completed"] = True
            xp_reward += 100  # бонус за все
        write_json("daily.json", daily)
        player = get_player()
        player["daily_completed"] = player.get("daily_completed", 0) + 1
        write_json("player.json", player)
        add_xp(xp_reward, f"Челлендж: {challenges[index]['text']}")
        return daily, xp_reward
    return daily, 0


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
        except Exception:
            mission = generate_weekly_mission()
    return mission


def generate_weekly_mission():
    projects = read_json("projects.json", {"projects": []})
    player = get_player()
    active = [p for p in projects.get("projects", []) if p.get("status") == "active"]
    level = player.get("level", 1)
    if not active:
        name = "Создай первый проект"
        tasks = [
            {"text": "Придумай идею для бизнеса", "done": False},
            {"text": "Создай проект в JARVIS", "done": False},
            {"text": "Проанализируй нишу", "done": False},
            {"text": "Напиши описание продукта", "done": False},
        ]
    elif level < 3:
        name = "Запусти MVP"
        tasks = [
            {"text": "Определи ЦА", "done": False},
            {"text": "Создай лендинг", "done": False},
            {"text": "Настрой аналитику", "done": False},
            {"text": "Получи первый отклик", "done": False},
        ]
    elif level < 7:
        name = "Масштабируй бизнес"
        tasks = [
            {"text": "Проанализируй 3 новых ниши", "done": False},
            {"text": "Запусти A/B тест", "done": False},
            {"text": "Найди партнёра", "done": False},
            {"text": "Увеличь конверсию на 10%", "done": False},
        ]
    else:
        name = "Выйди на новый уровень"
        tasks = [
            {"text": "Запусти новый продукт", "done": False},
            {"text": "Автоматизируй процесс", "done": False},
            {"text": "Делегируй 3 задачи", "done": False},
            {"text": "Достигни $1K MRR", "done": False},
        ]
    today = date.today()
    end = today + timedelta(days=(6 - today.weekday()))
    mission = {"name": name, "tasks": tasks, "xp_reward": 500,
               "week_start": today.isoformat(), "week_end": end.isoformat(), "completed": False}
    write_json("mission.json", mission)
    return mission


# ============================================================
# SPRINTS TRACKING
# ============================================================

def get_project_sprints(project_id):
    data = read_json("sprints.json", {"sprints": []})
    return [s for s in data["sprints"] if s.get("project_id") == project_id]


def create_sprint(project_id, name, tasks, duration_days=7):
    data = read_json("sprints.json", {"sprints": []})
    today = date.today()
    sprint = {
        "id": str(int(time.time() * 1000)),
        "project_id": project_id,
        "name": name,
        "number": len([s for s in data["sprints"] if s.get("project_id") == project_id]) + 1,
        "tasks": [{"text": t, "done": False} for t in tasks] if isinstance(tasks[0], str) else tasks,
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=duration_days)).isoformat(),
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    data["sprints"].append(sprint)
    write_json("sprints.json", data)
    return sprint


# ============================================================
# PAIN POINTS DATABASE
# ============================================================

def save_pain(pain_text, source="manual", niche="", url=""):
    pains = read_json("pains.json", {"pains": []})
    pain = {
        "id": str(int(time.time() * 1000)),
        "text": pain_text,
        "source": source,
        "niche": niche,
        "url": url,
        "status": "new",
        "created_at": datetime.now().isoformat()
    }
    pains["pains"].append(pain)
    write_json("pains.json", pains)
    return pain


# ============================================================
# DAILY PLANNER
# ============================================================

def generate_daily_plan():
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    mission = get_weekly_mission()
    daily = get_daily_challenge()

    active_projects = [p for p in projects.get("projects", []) if p.get("status") == "active"]
    active_quests = [q for q in quests.get("quests", []) if not q.get("completed")]
    urgent_quests = [q for q in active_quests if q.get("priority") == "urgent"]

    # Проекты с просроченными дедлайнами стадий
    stuck_projects = []
    today = date.today()
    for p in active_projects:
        stage = p.get("stage", "idea")
        history = p.get("stage_history", [])
        if history:
            last_change = history[-1].get("date", "")
            try:
                last_date = date.fromisoformat(last_change[:10])
                days_in_stage = (today - last_date).days
                deadline = STAGE_DEADLINE_DAYS.get(stage, 7)
                if deadline > 0 and days_in_stage > deadline:
                    stuck_projects.append({"project": p, "days": days_in_stage, "deadline": deadline})
            except Exception:
                pass

    plan = {
        "date": today.isoformat(),
        "sections": []
    }

    # Застрявшие проекты
    if stuck_projects:
        plan["sections"].append({
            "title": "🚨 Застрявшие проекты",
            "items": [f"⚠️ {s['project']['name']} — {s['days']} дней на стадии {FUNNEL_NAMES.get(s['project'].get('stage','idea'),'?')} (лимит {s['deadline']}д)"
                      for s in stuck_projects]
        })

    # Срочные квесты
    if urgent_quests:
        plan["sections"].append({
            "title": "🔴 Срочные квесты",
            "items": [f"⚔️ {q['name']} — {len([t for t in q.get('tasks',[]) if not t.get('done')])} задач осталось"
                      for q in urgent_quests[:5]]
        })

    # Миссия недели
    if mission and not mission.get("completed"):
        undone = [t for t in mission.get("tasks", []) if not t.get("done")]
        if undone:
            plan["sections"].append({
                "title": "🎯 Миссия недели",
                "items": [f"☐ {t['text']}" for t in undone]
            })

    # Ежедневные челленджи
    undone_challenges = [c for c in daily.get("challenges", []) if not c.get("done")]
    if undone_challenges:
        plan["sections"].append({
            "title": "📅 Ежедневные челленджи",
            "items": [f"☐ {c['text']} (+{c['xp']} XP)" for c in undone_challenges]
        })

    # Обычные квесты
    normal_quests = [q for q in active_quests if q.get("priority") != "urgent"][:3]
    if normal_quests:
        plan["sections"].append({
            "title": "⚔️ Квесты на сегодня",
            "items": [f"☐ {q['name']}" for q in normal_quests]
        })

    return plan


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


def get_tg_stats(chat_id):
    return get_user(chat_id, "stats", {"messages": 0, "modes": {}})


def update_tg_stats(chat_id):
    stats = get_tg_stats(chat_id)
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
        return "Ошибка поиска: " + str(e)


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


def parse_youtube_comments(video_url):
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(video_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.find("title")
        title_text = title.get_text() if title else "Unknown"
        description = soup.find("meta", {"name": "description"})
        desc_text = description.get("content", "") if description else ""
        return f"Видео: {title_text}\n\nОписание: {desc_text[:500]}"
    except Exception as e:
        return "Ошибка YouTube: " + str(e)


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
        except Exception:
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
            except Exception:
                pass
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
            return mp3_path
    except Exception:
        pass
    for p in [mp3_path, ogg_path]:
        if os.path.exists(p):
            os.remove(p)
    try:
        from gtts import gTTS
        fallback = f"/tmp/voice_{file_id}_gtts.mp3"
        gTTS(text=text, lang='ru').save(fallback)
        if os.path.exists(fallback) and os.path.getsize(fallback) > 100:
            return fallback
    except Exception:
        pass
    return None


# ============================================================
# AI ВЫЗОВ
# ============================================================

def call_ai(system_prompt, user_message, context=None):
    if context is None:
        context = []
    messages = [{"role": "system", "content": system_prompt}]
    for msg in context[-10:]:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("text", "")})
    messages.append({"role": "user", "content": user_message})
    try:
        resp = requests.post(GROQ_URL, headers={
            "Authorization": "Bearer " + (GROQ_API_KEY or ""),
            "Content-Type": "application/json",
        }, json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.9, "max_tokens": 3000}, timeout=60)
        if resp.status_code != 200:
            return "AI временно недоступен."
        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "Пустой ответ.")
    except Exception as e:
        print(f"AI error: {e}")
        return "Ошибка соединения с AI."


# ============================================================
# АВТОГЕНЕРАЦИЯ КВЕСТОВ
# ============================================================

def auto_generate_quests(project):
    prompt = f"""Создай 3 квеста для проекта.
Проект: {project.get('name', '')}
Описание: {project.get('description', '')}
Монетизация: {project.get('monetization', '')}
Ответь СТРОГО JSON массивом:
[{{"name": "квест", "priority": "urgent", "tasks": ["задача1", "задача2", "задача3"]}},
 {{"name": "квест", "priority": "normal", "tasks": ["задача1", "задача2", "задача3"]}},
 {{"name": "квест", "priority": "normal", "tasks": ["задача1", "задача2", "задача3"]}}]"""
    try:
        answer = call_ai("Отвечай ТОЛЬКО JSON.", prompt, [])
        start = answer.find('[')
        end = answer.rfind(']') + 1
        if start < 0 or end <= start:
            return []
        quest_data = json.loads(answer[start:end])
        quests_file = read_json("quests.json", {"quests": []})
        created = []
        for idx, q in enumerate(quest_data):
            tasks = [{"text": t, "done": False} for t in q.get("tasks", [])]
            quest = {
                "id": str(int(time.time() * 1000)) + str(idx),
                "name": q.get("name", "Квест"),
                "priority": q.get("priority", "normal"),
                "xp_reward": 250 if q.get("priority") == "urgent" else 150,
                "tasks": tasks, "completed": False,
                "project_id": project.get("id", ""),
                "created_at": datetime.now().isoformat()
            }
            quests_file["quests"].append(quest)
            created.append(quest)
        write_json("quests.json", quests_file)
        return created
    except Exception as e:
        print(f"Auto quest error: {e}")
        return []


def generate_offer(project):
    prompt = f"""Создай убойный оффер:
Проект: {project.get('name', '')}
Описание: {project.get('description', '')}
Монетизация: {project.get('monetization', '')}
Дай: 1.Заголовок 2.Подзаголовок 3.3 буллета 4.CTA 5.Гарантия 6.Цена"""
    return call_ai(JARVIS_SYSTEM_PROMPT, prompt, [])


# ============================================================
# TELEGRAM API
# ============================================================

def send_msg(chat_id, text, reply_kb=None, inline_kb=None):
    if not TELEGRAM_BOT_TOKEN:
        return []
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    sent = []
    while text:
        chunk = text[:4000]
        text = text[4000:]
        payload = {"chat_id": chat_id, "text": chunk}
        if not text and inline_kb:
            payload["reply_markup"] = inline_kb
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                mid = r.json().get("result", {}).get("message_id")
                if mid:
                    sent.append(mid)
        except Exception:
            pass
    if reply_kb:
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": "⌨️", "reply_markup": reply_kb}, timeout=30)
            if r.status_code == 200:
                mid = r.json().get("result", {}).get("message_id")
                if mid:
                    threading.Thread(target=lambda: (time.sleep(1), delete_msg(chat_id, mid)), daemon=True).start()
        except Exception:
            pass
    return sent


def delete_msg(chat_id, mid):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage",
                       json={"chat_id": chat_id, "message_id": mid}, timeout=10)
    except Exception:
        pass


def edit_msg(chat_id, mid, text, kb=None):
    if not TELEGRAM_BOT_TOKEN:
        return
    p = {"chat_id": chat_id, "message_id": mid, "text": text[:4000]}
    if kb:
        p["reply_markup"] = kb
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText", json=p, timeout=30)
    except Exception:
        pass


def send_photo(chat_id, path, caption=""):
    if not TELEGRAM_BOT_TOKEN or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                          data={"chat_id": chat_id, "caption": caption[:1000]},
                          files={"photo": ("img.jpg", f, "image/jpeg")}, timeout=60)
    except Exception:
        pass
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def send_voice(chat_id, path):
    if not TELEGRAM_BOT_TOKEN or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            ep = "sendVoice" if path.endswith(".ogg") else "sendAudio"
            k = "voice" if path.endswith(".ogg") else "audio"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{ep}",
                          data={"chat_id": chat_id}, files={k: f}, timeout=30)
    except Exception:
        pass
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def send_typing(chat_id):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction",
                       json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass


def answer_cb(cb_id, text=""):
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                       json={"callback_query_id": cb_id, "text": text}, timeout=10)
    except Exception:
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
        [{"text": v["name"], "callback_data": "tpl_" + k}] for k, v in TEMPLATES.items()
    ] + [[{"text": "⬅️ Назад", "callback_data": "back_main"}]]}


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
# TELEGRAM HANDLERS
# ============================================================

def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    cb_id = cb["id"]
    data = cb.get("data", "")
    old = cb["message"]["message_id"]

    if data.startswith("mode_"):
        mk = data[5:]
        if mk in MODES:
            set_user(chat_id, "mode", mk); set_user(chat_id, "context", []); set_user(chat_id, "waiting", "")
            answer_cb(cb_id, MODES[mk]["name"]); delete_msg(chat_id, old)
            send_msg(chat_id, MODES[mk]["emoji"] + " Режим: " + MODES[mk]["name"] + "\n\nЗадавай вопросы!",
                     reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
    elif data == "show_templates":
        answer_cb(cb_id); edit_msg(chat_id, old, "📦 Шаблоны:", tpl_inline_kb())
    elif data.startswith("tpl_"):
        k = data[4:]
        if k in TEMPLATES:
            answer_cb(cb_id, TEMPLATES[k]["name"]); delete_msg(chat_id, old); send_typing(chat_id); update_tg_stats(chat_id)
            a = call_ai(get_mode_prompt(chat_id), TEMPLATES[k]["prompt"], get_context(chat_id))
            add_context(chat_id, "user", TEMPLATES[k]["prompt"]); add_context(chat_id, "assistant", a)
            send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
    elif data == "show_tools":
        answer_cb(cb_id); edit_msg(chat_id, old, "🛠 Инструменты:", tools_inline_kb())
    elif data.startswith("tool_"):
        t = data[5:]
        answer_cb(cb_id); delete_msg(chat_id, old)
        prompts = {"search": "🔍 Запрос:", "parse": "🌐 Ссылка:", "image": "🖼 Опиши:", "voice": "🎙 Текст:",
                   "summarize": "📝 Текст:", "enru": "🇬🇧→🇷🇺 Текст:", "ruen": "🇷🇺→🇬🇧 Текст:"}
        if t == "clear":
            set_user(chat_id, "context", []); send_msg(chat_id, "🗑 Очищено!")
        elif t in prompts:
            set_user(chat_id, "waiting", t); send_msg(chat_id, prompts[t])
    elif data.startswith("act_"):
        a = data[4:]
        answer_cb(cb_id); delete_msg(chat_id, old)
        if a in ("more", "rewrite", "list", "example"):
            send_typing(chat_id)
            qs = {"more": "Подробнее.", "rewrite": "Перепиши лучше.", "list": "Оформи списком.", "example": "Пример с цифрами."}
            ans = call_ai(get_mode_prompt(chat_id), qs[a], get_context(chat_id))
            add_context(chat_id, "user", a); add_context(chat_id, "assistant", ans)
            send_msg(chat_id, ans, inline_kb=after_inline_kb())
        elif a == "image":
            send_typing(chat_id)
            p = call_ai("Отвечай ТОЛЬКО промтом.", "Короткий промт на английском. 10 слов.", get_context(chat_id)).strip().strip('"\'`')[:200]
            send_msg(chat_id, f"🎨 {p}\n⏳..."); send_photo(chat_id, generate_image(p), "🖼 " + p)
        elif a == "voice":
            ctx = get_context(chat_id)
            if ctx:
                send_msg(chat_id, "🎙 Создаю...")
                vp = create_voice(ctx[-1]["text"][:500])
                if vp: send_voice(chat_id, vp)
                else: send_msg(chat_id, "❌ Ошибка.")
        elif a == "fav":
            ctx = get_context(chat_id)
            if ctx: add_favorite(chat_id, ctx[-1]["text"])
        elif a == "note":
            ctx = get_context(chat_id)
            if ctx: add_note(chat_id, ctx[-1]["text"])
    elif data == "back_main":
        answer_cb(cb_id)
        mode = get_user(chat_id, "mode", DEFAULT_MODE)
        edit_msg(chat_id, old, "🤖 Jarvis 2.0 | " + MODES.get(mode, MODES[DEFAULT_MODE])["name"], main_inline_kb())


def handle_message(chat_id, text):
    text = text.strip()
    if text in ["/start", "/menu", "🏠 Меню", "⬅️ Назад в меню"]:
        send_msg(chat_id, "🤖 Jarvis 2.0\n\nВыбери режим:", reply_kb=main_reply_kb(), inline_kb=main_inline_kb()); return
    if text.startswith("/note "):
        add_note(chat_id, text[6:]); send_msg(chat_id, "📝 Сохранено!"); return
    if text in ["/stats", "📊 Статистика"]:
        s = get_tg_stats(chat_id); p = get_player()
        m = f"📊 Lv.{p.get('level',1)} ({p.get('rank','Новичок')})\n✨ {p.get('xp',0)}/{p.get('xp_to_next',1000)} XP\n🔥 {p.get('streak',0)}д (рек:{p.get('max_streak',0)})\n💬 {s.get('messages',0)} сообщ.\n🏆 {len(p.get('unlocked',[]))}/{len(ACHIEVEMENTS)}"
        send_msg(chat_id, m); return
    if text in MODE_BUTTONS:
        mk = MODE_BUTTONS[text]; set_user(chat_id, "mode", mk); set_user(chat_id, "context", []); set_user(chat_id, "waiting", "")
        send_msg(chat_id, MODES[mk]["emoji"] + " " + MODES[mk]["name"], reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return
    if text == "📦 Шаблоны":
        send_msg(chat_id, "📦 Шаблоны:", reply_kb=templates_reply_kb(), inline_kb=tpl_inline_kb()); return
    if text in TEMPLATE_BUTTONS:
        k = TEMPLATE_BUTTONS[text]; send_typing(chat_id); update_tg_stats(chat_id)
        a = call_ai(get_mode_prompt(chat_id), TEMPLATES[k]["prompt"], get_context(chat_id))
        add_context(chat_id, "user", TEMPLATES[k]["prompt"]); add_context(chat_id, "assistant", a)
        send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb()); return
    if text == "🛠 Инструменты":
        send_msg(chat_id, "🛠:", reply_kb=tools_reply_kb(), inline_kb=tools_inline_kb()); return

    tool_map = {"🔍 Поиск": "search", "🌐 Парсинг сайта": "parse", "🖼 Генерация фото": "image",
                "🎙 Озвучка текста": "voice", "📝 Суммаризация": "summarize",
                "🇬🇧→🇷🇺 Перевод EN-RU": "enru", "🇷🇺→🇬🇧 Перевод RU-EN": "ruen"}
    if text in tool_map:
        set_user(chat_id, "waiting", tool_map[text]); send_msg(chat_id, "Введи:"); return
    if text == "🗑 Очистить контекст":
        set_user(chat_id, "context", []); send_msg(chat_id, "🗑 Очищено!", reply_kb=main_reply_kb()); return
    if text == "📌 Избранное":
        favs = get_favorites(chat_id)
        send_msg(chat_id, "\n\n".join([f"{i+1}. {f['text'][:200]}" for i, f in enumerate(favs[-10:])]) if favs else "Пусто."); return
    if text == "📝 Заметки":
        notes = get_notes(chat_id)
        send_msg(chat_id, "\n\n".join([f"{i+1}. {n['text'][:200]}" for i, n in enumerate(notes[-10:])]) if notes else "Пусто. /note текст"); return

    quick = {"🔄 Подробнее": "Подробнее.", "✏️ Переписать": "Перепиши.", "📋 Список": "Списком.", "🎯 Пример": "Пример."}
    if text in quick:
        send_typing(chat_id); a = call_ai(get_mode_prompt(chat_id), quick[text], get_context(chat_id))
        add_context(chat_id, "user", text); add_context(chat_id, "assistant", a)
        send_msg(chat_id, a, inline_kb=after_inline_kb()); return
    if text == "🖼 Нарисовать":
        send_typing(chat_id); p = call_ai("Промт.", "Промт для картинки. 10 слов англ.", get_context(chat_id)).strip()[:200]
        send_msg(chat_id, f"🎨 {p}..."); send_photo(chat_id, generate_image(p), p); return
    if text == "🎙 Озвучить":
        ctx = get_context(chat_id)
        if ctx: send_msg(chat_id, "🎙..."); vp = create_voice(ctx[-1]["text"][:500]); send_voice(chat_id, vp) if vp else send_msg(chat_id, "❌")
        return
    if text == "📌 В избранное":
        ctx = get_context(chat_id)
        if ctx: add_favorite(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📌!")
        return
    if text == "📝 В заметки":
        ctx = get_context(chat_id)
        if ctx: add_note(chat_id, ctx[-1]["text"]); send_msg(chat_id, "📝!")
        return

    w = get_user(chat_id, "waiting", "")
    if w:
        set_user(chat_id, "waiting", ""); send_typing(chat_id)
        if w == "search":
            r = search_web(text); a = call_ai(get_mode_prompt(chat_id), f"Поиск '{text}':\n{r}\nАнализ.", get_context(chat_id))
            add_context(chat_id, "user", text); add_context(chat_id, "assistant", a)
            send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        elif w == "parse":
            c = parse_website(text); a = call_ai(get_mode_prompt(chat_id), f"Сайт:\n{c}\nАнализ.", get_context(chat_id))
            add_context(chat_id, "user", text); add_context(chat_id, "assistant", a)
            send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        elif w == "image":
            send_msg(chat_id, "🎨..."); send_photo(chat_id, generate_image(text), text[:200])
        elif w == "voice":
            send_msg(chat_id, "🎙..."); vp = create_voice(text[:500]); send_voice(chat_id, vp) if vp else send_msg(chat_id, "❌")
        elif w == "summarize":
            a = call_ai("Суммаризатор.", "5 мыслей:\n" + text[:3000], [])
            add_context(chat_id, "user", "Сумм"); add_context(chat_id, "assistant", a)
            send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        elif w in ("enru", "ruen"):
            lang = "русский" if w == "enru" else "английский"
            a = call_ai("Переводчик.", f"На {lang}:\n{text}", [])
            send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())
        return

    send_typing(chat_id); update_tg_stats(chat_id); track_activity("message")
    a = call_ai(get_mode_prompt(chat_id), text, get_context(chat_id))
    add_context(chat_id, "user", text); add_context(chat_id, "assistant", a)
    add_xp(25, f"Чат: {text[:50]}")
    send_msg(chat_id, a, reply_kb=after_reply_kb(), inline_kb=after_inline_kb())


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json()
        if not data:
            return "ok"
        if "callback_query" in data:
            try: handle_callback(data["callback_query"])
            except Exception as e: print(f"CB err: {e}")
            return "ok"
        msg = data.get("message", {})
        cid = msg.get("chat", {}).get("id")
        txt = msg.get("text", "")
        if cid and txt:
            try: handle_message(cid, txt)
            except Exception as e: print(f"Msg err: {e}"); send_msg(cid, "Ошибка.")
    except Exception as e:
        print(f"Webhook err: {e}")
    return "ok"


@app.route("/", methods=["GET"])
def home():
    return "Jarvis 2.0 is running!"


@app.route("/chat")
def web_chat():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}", 500


# === WEB API — CHAT ===

web_sessions = {}

def get_web_session(sid):
    if sid not in web_sessions:
        web_sessions[sid] = {"mode": "helper", "context": []}
    return web_sessions[sid]


@app.route("/api/send", methods=["POST"])
def api_send():
    try:
        d = request.get_json(); sid = d.get("session_id", ""); txt = d.get("text", "").strip()
        if not sid or not txt:
            return json.dumps({"error": "empty"}), 400, {"Content-Type": "application/json"}
        s = get_web_session(sid)
        s["context"].append({"role": "user", "text": txt[:1000]})
        s["context"] = s["context"][-20:]
        a = call_ai(MODES.get(s["mode"], MODES["helper"])["prompt"], txt, s["context"])
        s["context"].append({"role": "assistant", "text": a[:1000]})
        s["context"] = s["context"][-20:]
        track_activity("message"); add_xp(25, f"Web: {txt[:50]}")
        return json.dumps({"answer": a, "time": time.strftime("%H:%M")}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/mode", methods=["POST"])
def api_mode():
    try:
        d = request.get_json(); sid = d.get("session_id", ""); m = d.get("mode", "helper")
        if sid and m in MODES:
            s = get_web_session(sid); s["mode"] = m; s["context"] = []
            return json.dumps({"ok": True, "mode": MODES[m]}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "invalid"}), 400, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/clear", methods=["POST"])
def api_clear():
    try:
        d = request.get_json(); sid = d.get("session_id", "")
        if sid in web_sessions: web_sessions[sid] = {"mode": "helper", "context": []}
        return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === PROJECTS ===

@app.route("/api/projects", methods=["GET"])
def api_get_projects():
    try:
        d = read_json("projects.json", {"projects": []})
        ps = d.get("projects", [])
        st = request.args.get("status", ""); sg = request.args.get("stage", ""); tg = request.args.get("tag", "")
        if st: ps = [p for p in ps if p.get("status") == st]
        if sg: ps = [p for p in ps if p.get("stage") == sg]
        if tg: ps = [p for p in ps if tg in p.get("tags", [])]
        return json.dumps({"projects": ps}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    try:
        r = request.get_json(); d = read_json("projects.json", {"projects": []})
        p = {
            "id": str(int(time.time() * 1000)), "name": r.get("name", "Без названия"),
            "description": r.get("description", ""), "monetization": r.get("monetization", ""),
            "status": "active", "stage": "idea", "tags": r.get("tags", []),
            "stage_history": [{"to": "idea", "date": datetime.now().isoformat()}],
            "sprint": 1, "revenue": 0, "revenue_history": [],
            "links": [], "notes": [], "score": None,
            "created_at": datetime.now().isoformat()
        }
        d["projects"].append(p); write_json("projects.json", d)
        add_xp(100, f"Проект: {p['name']}")
        threading.Thread(target=auto_generate_quests, args=(p,), daemon=True).start()
        return json.dumps(p, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>", methods=["GET"])
def api_get_project(pid):
    try:
        d = read_json("projects.json", {"projects": []})
        for p in d["projects"]:
            if p["id"] == pid:
                q = read_json("quests.json", {"quests": []})
                p["quests"] = [x for x in q["quests"] if x.get("project_id") == pid]
                p["sprints"] = get_project_sprints(pid)
                # Проверка дедлайна стадии
                stage = p.get("stage", "idea")
                hist = p.get("stage_history", [])
                if hist:
                    try:
                        last = date.fromisoformat(hist[-1].get("date", "")[:10])
                        days = (date.today() - last).days
                        deadline = STAGE_DEADLINE_DAYS.get(stage, 7)
                        p["days_in_stage"] = days
                        p["stage_deadline"] = deadline
                        p["stage_overdue"] = deadline > 0 and days > deadline
                    except Exception:
                        pass
                return json.dumps(p, ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>", methods=["PUT"])
def api_update_project(pid):
    try:
        d = read_json("projects.json", {"projects": []}); r = request.get_json()
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                for f in ["name", "description", "monetization", "status", "sprint", "tags"]:
                    if f in r: d["projects"][i][f] = r[f]
                write_json("projects.json", d)
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>", methods=["DELETE"])
def api_delete_project(pid):
    try:
        d = read_json("projects.json", {"projects": []})
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                d["projects"][i]["status"] = "archived"
                d["projects"][i]["archived_at"] = datetime.now().isoformat()
                write_json("projects.json", d)
                return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/restore", methods=["POST"])
def api_restore_project(pid):
    try:
        d = read_json("projects.json", {"projects": []})
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                d["projects"][i]["status"] = "active"; d["projects"][i].pop("archived_at", None)
                write_json("projects.json", d)
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/stage", methods=["PUT"])
def api_update_stage(pid):
    try:
        d = read_json("projects.json", {"projects": []}); r = request.get_json()
        ns = r.get("stage", "idea")
        if ns not in FUNNEL_STAGES:
            return json.dumps({"error": "Invalid"}), 400, {"Content-Type": "application/json"}
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                os_ = p.get("stage", "idea"); d["projects"][i]["stage"] = ns
                h = d["projects"][i].get("stage_history", [])
                h.append({"from": os_, "to": ns, "date": datetime.now().isoformat()})
                d["projects"][i]["stage_history"] = h
                write_json("projects.json", d)
                oi = FUNNEL_STAGES.index(os_) if os_ in FUNNEL_STAGES else 0
                ni = FUNNEL_STAGES.index(ns)
                if ni > oi: add_xp(FUNNEL_XP.get(ns, 0), f"Стадия: {FUNNEL_NAMES[ns]}")
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/revenue", methods=["POST"])
def api_add_revenue(pid):
    try:
        d = read_json("projects.json", {"projects": []}); r = request.get_json()
        amt = r.get("amount", 0)
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                d["projects"][i]["revenue"] = d["projects"][i].get("revenue", 0) + amt
                rh = d["projects"][i].get("revenue_history", [])
                rh.append({"amount": amt, "date": datetime.now().isoformat(), "note": r.get("note", "")})
                d["projects"][i]["revenue_history"] = rh
                write_json("projects.json", d); add_xp(50, f"+${amt}")
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/links", methods=["POST"])
def api_add_link(pid):
    try:
        d = read_json("projects.json", {"projects": []}); r = request.get_json()
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                ls = d["projects"][i].get("links", [])
                ls.append({"id": str(int(time.time()*1000)), "url": r.get("url",""), "title": r.get("title",""), "added": datetime.now().isoformat()})
                d["projects"][i]["links"] = ls; write_json("projects.json", d)
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/links/<lid>", methods=["DELETE"])
def api_delete_link(pid, lid):
    try:
        d = read_json("projects.json", {"projects": []})
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                d["projects"][i]["links"] = [l for l in p.get("links", []) if l.get("id") != lid]
                write_json("projects.json", d)
                return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/notes", methods=["POST"])
def api_add_note(pid):
    try:
        d = read_json("projects.json", {"projects": []}); r = request.get_json()
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                ns = d["projects"][i].get("notes", [])
                ns.append({"id": str(int(time.time()*1000)), "text": r.get("text",""), "added": datetime.now().isoformat()})
                d["projects"][i]["notes"] = ns; write_json("projects.json", d)
                return json.dumps(d["projects"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/notes/<nid>", methods=["DELETE"])
def api_delete_note(pid, nid):
    try:
        d = read_json("projects.json", {"projects": []})
        for i, p in enumerate(d["projects"]):
            if p["id"] == pid:
                d["projects"][i]["notes"] = [n for n in p.get("notes", []) if n.get("id") != nid]
                write_json("projects.json", d)
                return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/projects/<pid>/offer", methods=["POST"])
def api_offer(pid):
    try:
        d = read_json("projects.json", {"projects": []})
        for p in d["projects"]:
            if p["id"] == pid:
                o = generate_offer(p); add_xp(50, f"Оффер: {p.get('name','')}")
                return json.dumps({"offer": o}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === FUNNEL ===

@app.route("/api/funnel", methods=["GET"])
def api_funnel():
    try:
        d = read_json("projects.json", {"projects": []})
        f = {}
        for s in FUNNEL_STAGES:
            f[s] = {"name": FUNNEL_NAMES[s], "projects": [p for p in d["projects"] if p.get("stage","idea")==s and p.get("status")!="archived"]}
        return json.dumps(f, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === QUESTS ===

@app.route("/api/quests", methods=["GET"])
def api_get_quests():
    try:
        d = read_json("quests.json", {"quests": []})
        pid = request.args.get("project_id", "")
        if pid: d["quests"] = [q for q in d["quests"] if q.get("project_id") == pid]
        return json.dumps(d, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quests", methods=["POST"])
def api_create_quest():
    try:
        d = read_json("quests.json", {"quests": []}); r = request.get_json()
        ts = [{"text": t, "done": False} if isinstance(t, str) else t for t in r.get("tasks", [])]
        q = {"id": str(int(time.time()*1000)), "name": r.get("name",""), "priority": r.get("priority","normal"),
             "xp_reward": r.get("xp_reward",100), "tasks": ts, "completed": False,
             "project_id": r.get("project_id",""), "created_at": datetime.now().isoformat()}
        d["quests"].append(q); write_json("quests.json", d)
        return json.dumps(q, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quests/<qid>", methods=["PUT"])
def api_update_quest(qid):
    try:
        d = read_json("quests.json", {"quests": []}); r = request.get_json()
        for i, q in enumerate(d["quests"]):
            if q["id"] == qid:
                wc = q.get("completed", False); d["quests"][i].update(r)
                if r.get("completed") and not wc:
                    add_xp(q.get("xp_reward",100), f"Квест: {q.get('name','')}")
                    d["quests"][i]["completed_at"] = datetime.now().isoformat()
                write_json("quests.json", d)
                return json.dumps(d["quests"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quests/<qid>", methods=["DELETE"])
def api_delete_quest(qid):
    try:
        d = read_json("quests.json", {"quests": []})
        d["quests"] = [q for q in d["quests"] if q["id"] != qid]; write_json("quests.json", d)
        return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/quests/<qid>/toggle-task", methods=["POST"])
def api_toggle_task(qid):
    try:
        d = read_json("quests.json", {"quests": []}); r = request.get_json(); idx = r.get("index", 0)
        for i, q in enumerate(d["quests"]):
            if q["id"] == qid:
                ts = q.get("tasks", [])
                if 0 <= idx < len(ts):
                    ts[idx]["done"] = not ts[idx]["done"]; d["quests"][i]["tasks"] = ts
                    if all(t.get("done") for t in ts) and not q.get("completed"):
                        d["quests"][i]["completed"] = True
                        d["quests"][i]["completed_at"] = datetime.now().isoformat()
                        add_xp(q.get("xp_reward",100), f"Квест: {q.get('name','')}")
                    write_json("quests.json", d)
                    return json.dumps(d["quests"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === SPRINTS ===

@app.route("/api/sprints", methods=["GET"])
def api_get_sprints():
    try:
        d = read_json("sprints.json", {"sprints": []})
        pid = request.args.get("project_id", "")
        if pid: d["sprints"] = [s for s in d["sprints"] if s.get("project_id") == pid]
        return json.dumps(d, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/sprints", methods=["POST"])
def api_create_sprint():
    try:
        r = request.get_json()
        tasks = r.get("tasks", [])
        s = create_sprint(r.get("project_id", ""), r.get("name", "Спринт"), tasks, r.get("duration", 7))
        return json.dumps(s, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/sprints/<sid>/toggle-task", methods=["POST"])
def api_toggle_sprint_task(sid):
    try:
        d = read_json("sprints.json", {"sprints": []}); r = request.get_json(); idx = r.get("index", 0)
        for i, s in enumerate(d["sprints"]):
            if s["id"] == sid:
                ts = s.get("tasks", [])
                if 0 <= idx < len(ts):
                    ts[idx]["done"] = not ts[idx]["done"]; d["sprints"][i]["tasks"] = ts
                    if all(t.get("done") for t in ts) and not s.get("completed"):
                        d["sprints"][i]["completed"] = True
                        d["sprints"][i]["completed_at"] = datetime.now().isoformat()
                        player = get_player()
                        player["completed_sprints"] = player.get("completed_sprints", 0) + 1
                        write_json("player.json", player)
                        add_xp(300, f"Спринт: {s.get('name','')}")
                    write_json("sprints.json", d)
                    return json.dumps(d["sprints"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === PLAYER ===

@app.route("/api/player", methods=["GET"])
def api_player():
    try:
        return json.dumps(get_player(), ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/player/add-xp", methods=["POST"])
def api_add_xp():
    try:
        r = request.get_json(); p, l, a = add_xp(r.get("amount", 0), r.get("reason", ""))
        return json.dumps({"player": p, "leveled": l, "new_achievements": [{"name": x["name"], "icon": x["icon"]} for x in a]},
                          ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/achievements", methods=["GET"])
def api_achievements():
    try:
        p = get_player(); u = p.get("unlocked", [])
        r = [{"id": k, "name": v["name"], "icon": v["icon"], "desc": v["desc"], "unlocked": k in u} for k, v in ACHIEVEMENTS.items()]
        return json.dumps(r, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/mission", methods=["GET"])
def api_mission():
    try:
        return json.dumps(get_weekly_mission(), ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/mission/toggle", methods=["POST"])
def api_toggle_mission():
    try:
        r = request.get_json(); idx = r.get("index", 0); m = get_weekly_mission()
        if 0 <= idx < len(m.get("tasks", [])):
            m["tasks"][idx]["done"] = not m["tasks"][idx]["done"]
            if all(t["done"] for t in m["tasks"]) and not m.get("completed"):
                add_xp(m.get("xp_reward", 500), "Миссия!"); m["completed"] = True
            write_json("mission.json", m)
        return json.dumps(m, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === DAILY CHALLENGE ===

@app.route("/api/daily", methods=["GET"])
def api_daily():
    try:
        return json.dumps(get_daily_challenge(), ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/daily/complete", methods=["POST"])
def api_complete_daily():
    try:
        r = request.get_json(); d, xp = complete_daily_challenge(r.get("index", 0))
        return json.dumps({"daily": d, "xp_earned": xp}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === DAILY PLANNER ===

@app.route("/api/daily-plan", methods=["GET"])
def api_daily_plan():
    try:
        return json.dumps(generate_daily_plan(), ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === PAINS DATABASE ===

@app.route("/api/pains", methods=["GET"])
def api_get_pains():
    try:
        d = read_json("pains.json", {"pains": []})
        return json.dumps(d, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/pains", methods=["POST"])
def api_save_pain():
    try:
        r = request.get_json()
        p = save_pain(r.get("text", ""), r.get("source", "manual"), r.get("niche", ""), r.get("url", ""))
        add_xp(20, "Боль сохранена")
        return json.dumps(p, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/pains/<pain_id>", methods=["PUT"])
def api_update_pain(pain_id):
    try:
        d = read_json("pains.json", {"pains": []}); r = request.get_json()
        for i, p in enumerate(d["pains"]):
            if p["id"] == pain_id:
                for f in ["status", "niche", "text"]:
                    if f in r: d["pains"][i][f] = r[f]
                write_json("pains.json", d)
                return json.dumps(d["pains"][i], ensure_ascii=False), 200, {"Content-Type": "application/json"}
        return json.dumps({"error": "Не найден"}), 404, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/pains/<pain_id>", methods=["DELETE"])
def api_delete_pain(pain_id):
    try:
        d = read_json("pains.json", {"pains": []})
        d["pains"] = [p for p in d["pains"] if p["id"] != pain_id]; write_json("pains.json", d)
        return json.dumps({"ok": True}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === TAGS ===

@app.route("/api/tags", methods=["GET"])
def api_tags():
    try:
        return json.dumps({"tags": DEFAULT_TAGS}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === ANALYTICS ===

@app.route("/api/analyze-niche", methods=["POST"])
def api_analyze_niche():
    try:
        r = request.get_json(); n = r.get("niche", "")
        a = call_ai(JARVIS_SYSTEM_PROMPT, f"Анализ ниши: {n}\n📊🎯💰⚡🕐📈✅ + 3 риска, 3 конкурента, стратегия, план 4 нед.", [])
        track_activity("niche"); add_xp(50, f"Ниша: {n}")
        return json.dumps({"analysis": a}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/generate-sprints", methods=["POST"])
def api_gen_sprints():
    try:
        r = request.get_json()
        a = call_ai(JARVIS_SYSTEM_PROMPT, f"Разбей на {r.get('weeks',4)} спринтов:\n{r.get('project','')}\nЦель, 4-6 задач, критерий.", [])
        return json.dumps({"sprints": a}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/score-idea", methods=["POST"])
def api_score():
    try:
        r = request.get_json()
        a = call_ai("ТОЛЬКО JSON.", f'Оцени идею 1-10: {r.get("idea","")}\n{{"market":8,"competition":6,"mvp_speed":9,"monetization":7,"scalability":5,"total":70,"verdict":"..."}}', [])
        try:
            s = a.find('{'); e = a.rfind('}')+1
            sc = json.loads(a[s:e]) if s >= 0 and e > s else {"total": 0, "verdict": a}
        except Exception:
            sc = {"total": 0, "verdict": a}
        track_activity("niche")
        return json.dumps(sc, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/reddit-search", methods=["POST"])
def api_reddit():
    try:
        r = request.get_json(); q = r.get("query", "")
        resp = requests.get(f"https://www.reddit.com/search.json?q={urllib.parse.quote(q)}&sort=relevance&limit=10",
                            headers={"User-Agent": "JarvisBot/2.0"}, timeout=10)
        if resp.status_code != 200:
            return json.dumps({"error": "Reddit down"}), 500, {"Content-Type": "application/json"}
        posts = []
        for p in resp.json().get("data", {}).get("children", []):
            d = p.get("data", {})
            posts.append({"title": d.get("title",""), "subreddit": d.get("subreddit",""),
                          "score": d.get("score",0), "comments": d.get("num_comments",0),
                          "url": f"https://reddit.com{d.get('permalink','')}", "text": d.get("selftext","")[:300]})
        analysis = call_ai(JARVIS_SYSTEM_PROMPT, f"Reddit боли:\n{json.dumps(posts[:5], ensure_ascii=False)[:3000]}\n\n1.Топ-5 болей 2.Что покупают 3.3 идеи", [])
        track_activity("niche"); add_xp(30, f"Reddit: {q}")
        return json.dumps({"posts": posts, "analysis": analysis}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/youtube-analyze", methods=["POST"])
def api_youtube():
    try:
        r = request.get_json(); url = r.get("url", "")
        content = parse_youtube_comments(url)
        a = call_ai(JARVIS_SYSTEM_PROMPT, f"YouTube видео:\n{content}\n\nВыдели: 1.Боли 2.Запросы 3.Идеи для бизнеса", [])
        track_activity("niche"); add_xp(30, "YouTube")
        return json.dumps({"content": content, "analysis": a}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/trends", methods=["POST"])
def api_trends():
    try:
        r = request.get_json(); q = r.get("query", "")
        sr = search_web(f"{q} trends 2024 2025 growth market size")
        a = call_ai(JARVIS_SYSTEM_PROMPT, f"Тренды: {q}\nДанные:\n{sr[:2000]}\n📈📊🌍💰🔮⚡", [])
        track_activity("niche"); add_xp(30, f"Тренды: {q}")
        return json.dumps({"query": q, "analysis": a}, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === HISTORY ===

@app.route("/api/history", methods=["GET"])
def api_history():
    try:
        return json.dumps(read_json("history.json", {"entries": []}), ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === EXPORT/IMPORT ===

@app.route("/api/export", methods=["GET"])
def api_export():
    try:
        exp = {"exported_at": datetime.now().isoformat(), "version": "2.1",
               "player": get_player(), "projects": read_json("projects.json", {"projects": []}),
               "quests": read_json("quests.json", {"quests": []}), "sprints": read_json("sprints.json", {"sprints": []}),
               "activity": read_json("activity.json", {}), "mission": read_json("mission.json", {}),
               "history": read_json("history.json", {"entries": []}), "pains": read_json("pains.json", {"pains": []}),
               "daily": read_json("daily.json", {})}
        return json.dumps(exp, ensure_ascii=False, indent=2), 200, {
            "Content-Type": "application/json", "Content-Disposition": "attachment; filename=jarvis_backup.json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/import", methods=["POST"])
def api_import():
    try:
        d = request.get_json()
        if not d:
            return json.dumps({"error": "empty"}), 400, {"Content-Type": "application/json"}
        files = {"player": "player.json", "projects": "projects.json", "quests": "quests.json",
                 "sprints": "sprints.json", "activity": "activity.json", "mission": "mission.json",
                 "history": "history.json", "pains": "pains.json", "daily": "daily.json"}
        imported = []
        for k, f in files.items():
            if k in d: write_json(f, d[k]); imported.append(k)
        return json.dumps({"ok": True, "imported": imported}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


# === STATS ===

@app.route("/api/stats", methods=["GET"])
def api_stats():
    try:
        projects = read_json("projects.json", {"projects": []})
        quests = read_json("quests.json", {"quests": []})
        sprints = read_json("sprints.json", {"sprints": []})
        player = get_player()
        activity = read_json("activity.json", {"total_messages": 0, "niches_analyzed": 0})
        pains = read_json("pains.json", {"pains": []})
        pl = projects.get("projects", []); ql = quests.get("quests", []); sl = sprints.get("sprints", [])
        active = [p for p in pl if p.get("status") == "active"]
        funnel = {}
        for s in FUNNEL_STAGES:
            funnel[s] = {"name": FUNNEL_NAMES[s], "count": len([p for p in active if p.get("stage","idea")==s])}
        # Stuck projects
        stuck = []
        for p in active:
            h = p.get("stage_history", [])
            if h:
                try:
                    ld = date.fromisoformat(h[-1].get("date","")[:10])
                    days = (date.today() - ld).days
                    dl = STAGE_DEADLINE_DAYS.get(p.get("stage","idea"), 7)
                    if dl > 0 and days > dl:
                        stuck.append({"id": p["id"], "name": p["name"], "stage": p.get("stage"), "days": days, "deadline": dl})
                except Exception:
                    pass
        return json.dumps({
            "active_projects": len(active), "total_projects": len(pl),
            "archived_projects": len([p for p in pl if p.get("status")=="archived"]),
            "total_revenue": sum(p.get("revenue",0) for p in pl),
            "active_quests": len([q for q in ql if not q.get("completed")]),
            "completed_quests": len([q for q in ql if q.get("completed")]),
            "total_quests": len(ql),
            "active_sprints": len([s for s in sl if not s.get("completed")]),
            "completed_sprints": len([s for s in sl if s.get("completed")]),
            "total_messages": activity.get("total_messages", 0),
            "niches_analyzed": activity.get("niches_analyzed", 0),
            "saved_pains": len(pains.get("pains", [])),
            "player": player, "funnel": funnel, "stuck_projects": stuck,
            "achievements_unlocked": len(player.get("unlocked", [])),
            "achievements_total": len(ACHIEVEMENTS)
        }, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/api/modes", methods=["GET"])
def api_modes():
    try:
        return json.dumps(MODES, ensure_ascii=False), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


@app.route("/health", methods=["GET"])
def health():
    try:
        return json.dumps({"status": "ok", "version": "2.1", "time": datetime.now().isoformat(),
                           "files": [f.name for f in DATA_DIR.iterdir()] if DATA_DIR.exists() else []}), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}), 500, {"Content-Type": "application/json"}


# ============================================================
# ЗАПУСК
# ============================================================

def setup_webhook():
    if RENDER_URL and TELEGRAM_BOT_TOKEN:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
                              json={"url": RENDER_URL + "/webhook"}, timeout=10)
            print("Webhook:", r.json())
        except Exception as e:
            print("Webhook error:", e)


def keep_alive():
    while True:
        time.sleep(600)
        if RENDER_URL:
            try: requests.get(RENDER_URL, timeout=10)
            except Exception: pass


if __name__ == "__main__":
    setup_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    print(f"\n{'='*50}")
    print(f"🤖 JARVIS 2.1 — http://localhost:{port}")
    print(f"📊 Web — http://localhost:{port}/chat")
    print(f"📡 API — http://localhost:{port}/api/stats")
    print(f"💾 Export — http://localhost:{port}/api/export")
    print(f"❤️ Health — http://localhost:{port}/health")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port)
