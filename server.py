"""
============================================================
JARVIS 2.0 — Обновлённый сервер
============================================================
ЧТО ИЗМЕНИЛОСЬ:
- Добавлены роуты для проектов, квестов, геймификации
- Добавлен анализ ниш через Claude
- Добавлена генерация спринтов
- Всё остальное — как было (Flask + Anthropic)

НЕЙРОНКА: та же — Claude (Anthropic Python SDK)
============================================================
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = Flask(__name__)
CORS(app)

# === НЕЙРОНКА: та же — Claude через Anthropic SDK ===
client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

MODEL = os.getenv("MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8192"))

# === ПАПКА ДЛЯ ДАННЫХ ===
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# === СИСТЕМНЫЙ ПРОМТ JARVIS (обновлённый) ===
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


# ============================================================
# УТИЛИТЫ ДЛЯ РАБОТЫ С JSON-ФАЙЛАМИ
# ============================================================

def read_json(filename, default=None):
    """Читает JSON файл из папки data/"""
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
    """Записывает JSON файл в папку data/"""
    filepath = DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_player():
    """Получает данные игрока (XP, уровень)"""
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
    """Добавляет XP и проверяет левел-ап"""
    ranks = [
        "Новичок", "Стажёр", "Предприниматель", "Бизнесмен",
        "Стратег", "Магнат", "Титан", "Легенда"
    ]
    
    player = get_player()
    player["xp"] += amount
    
    # Левел-ап
    while player["xp"] >= player["xp_to_next"]:
        player["xp"] -= player["xp_to_next"]
        player["level"] += 1
        player["xp_to_next"] = int(player["xp_to_next"] * 1.3)
        rank_idx = min(player["level"] // 5, len(ranks) - 1)
        player["rank"] = ranks[rank_idx]
    
    write_json("player.json", player)
    return player


# ============================================================
# РОУТЫ — СТРАНИЦА
# ============================================================

@app.route("/")
def index():
    """Главная страница — отдаём обновлённый HTML"""
    return render_template("index.html")


# ============================================================
# РОУТЫ — ЧАТ С CLAUDE (как было, но с обновлённым промтом)
# ============================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Основной чат с JARVIS.
    Отправляет сообщение в Claude и возвращает ответ.
    НЕЙРОНКА: Claude (Anthropic) — та же самая.
    """
    try:
        data = request.json
        message = data.get("message", "").strip()
        context = data.get("context", [])
        
        if not message:
            return jsonify({"error": "Пустое сообщение"}), 400
        
        # Формируем историю сообщений
        messages = []
        for msg in context[-20:]:  # Последние 20 для контекста
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        messages.append({"role": "user", "content": message})
        
        # === ОТПРАВЛЯЕМ В CLAUDE ===
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=JARVIS_SYSTEM_PROMPT,
            messages=messages
        )
        
        reply = response.content[0].text
        
        # +25 XP за сообщение
        add_xp(25, f"Чат: {message[:50]}")
        
        return jsonify({
            "reply": reply,
            "tokens": {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens
            },
            "model": response.model,
            "timestamp": datetime.now().isoformat()
        })
        
    except anthropic.AuthenticationError:
        return jsonify({"error": "Неверный API ключ. Проверь .env"}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "Лимит запросов Claude. Подожди."}), 429
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# НОВОЕ: АНАЛИЗ НИШИ
# ============================================================

@app.route("/api/analyze-niche", methods=["POST"])
def analyze_niche():
    """Быстрый анализ бизнес-ниши через Claude"""
    try:
        data = request.json
        niche = data.get("niche", "")
        description = data.get("description", "")
        
        prompt = f"""Проанализируй бизнес-нишу и дай структурированную оценку.

Ниша: {niche}
Описание: {description or 'Нет описания'}

Дай оценку в формате БИЗНЕС-ОЦЕНКИ.
Также добавь:
- 3 главных риска
- 3 конкурента
- Стратегию входа
- План на 4 недели (4 спринта)"""

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=JARVIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        add_xp(50, f"Анализ ниши: {niche}")
        
        return jsonify({
            "analysis": response.content[0].text,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# НОВОЕ: ГЕНЕРАЦИЯ СПРИНТОВ
# ============================================================

@app.route("/api/generate-sprints", methods=["POST"])
def generate_sprints():
    """Разбивает проект на недельные спринты через Claude"""
    try:
        data = request.json
        project = data.get("project", "")
        weeks = data.get("weeks", 4)
        
        prompt = f"""Разбей проект на {weeks} недельных спринтов.

Проект: {project}

Для каждого спринта:
1. Цель (одно предложение)
2. 4-6 задач (чек-лист)
3. Критерий готовности
4. Ожидаемый результат"""

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=JARVIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return jsonify({
            "sprints": response.content[0].text,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# НОВОЕ: CRUD ДЛЯ ПРОЕКТОВ
# ============================================================

@app.route("/api/projects", methods=["GET"])
def get_projects():
    data = read_json("projects.json", {"projects": []})
    return jsonify(data)


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = read_json("projects.json", {"projects": []})
    new_project = {
        "id": str(int(time.time() * 1000)),
        "name": request.json.get("name", "Без названия"),
        "description": request.json.get("description", ""),
        "monetization": request.json.get("monetization", ""),
        "status": "active",
        "sprint": 1,
        "revenue": 0,
        "created_at": datetime.now().isoformat()
    }
    data["projects"].append(new_project)
    write_json("projects.json", data)
    
    add_xp(100, f"Новый проект: {new_project['name']}")
    
    return jsonify(new_project)


@app.route("/api/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    data = read_json("projects.json", {"projects": []})
    for i, p in enumerate(data["projects"]):
        if p["id"] == project_id:
            data["projects"][i].update(request.json)
            write_json("projects.json", data)
            return jsonify(data["projects"][i])
    return jsonify({"error": "Не найден"}), 404


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    data = read_json("projects.json", {"projects": []})
    data["projects"] = [p for p in data["projects"] if p["id"] != project_id]
    write_json("projects.json", data)
    return jsonify({"success": True})


# ============================================================
# НОВОЕ: КВЕСТЫ
# ============================================================

@app.route("/api/quests", methods=["GET"])
def get_quests():
    return jsonify(read_json("quests.json", {"quests": []}))


@app.route("/api/quests", methods=["POST"])
def create_quest():
    data = read_json("quests.json", {"quests": []})
    quest = {
        "id": str(int(time.time() * 1000)),
        "name": request.json.get("name", ""),
        "priority": request.json.get("priority", "normal"),
        "xp_reward": request.json.get("xp_reward", 100),
        "tasks": request.json.get("tasks", []),
        "completed": False,
        "created_at": datetime.now().isoformat()
    }
    data["quests"].append(quest)
    write_json("quests.json", data)
    return jsonify(quest)


@app.route("/api/quests/<quest_id>", methods=["PUT"])
def update_quest(quest_id):
    data = read_json("quests.json", {"quests": []})
    for i, q in enumerate(data["quests"]):
        if q["id"] == quest_id:
            data["quests"][i].update(request.json)
            if request.json.get("completed"):
                add_xp(q.get("xp_reward", 100), f"Квест: {q['name']}")
            write_json("quests.json", data)
            return jsonify(data["quests"][i])
    return jsonify({"error": "Не найден"}), 404


# ============================================================
# НОВОЕ: ИГРОК (XP, УРОВЕНЬ)
# ============================================================

@app.route("/api/player", methods=["GET"])
def get_player_route():
    return jsonify(get_player())


@app.route("/api/player/add-xp", methods=["POST"])
def add_xp_route():
    amount = request.json.get("amount", 0)
    reason = request.json.get("reason", "")
    player = add_xp(amount, reason)
    return jsonify(player)


# ============================================================
# НОВОЕ: СТАТИСТИКА
# ============================================================

@app.route("/api/stats", methods=["GET"])
def get_stats():
    projects = read_json("projects.json", {"projects": []})
    quests = read_json("quests.json", {"quests": []})
    player = get_player()
    
    active = [p for p in projects["projects"] if p.get("status") == "active"]
    total_rev = sum(p.get("revenue", 0) for p in projects["projects"])
    
    return jsonify({
        "active_projects": len(active),
        "total_projects": len(projects["projects"]),
        "total_revenue": total_rev,
        "active_quests": len([q for q in quests["quests"] if not q.get("completed")]),
        "completed_quests": len([q for q in quests["quests"] if q.get("completed")]),
        "player": player
    })


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    
    print("")
    print("╔══════════════════════════════════════╗")
    print("║                                      ║")
    print("║     🤖 JARVIS 2.0 — ЗАПУЩЕН          ║")
    print("║                                      ║")
    print(f"║     🌐 http://localhost:{port}          ║")
    print("║     📡 Нейронка: Claude (Anthropic)   ║")
    print("║     🐍 Python + Flask                 ║")
    print("║     💾 Данные: ./data/                ║")
    print("║                                      ║")
    print("╚══════════════════════════════════════╝")
    print("")
    
    app.run(host="0.0.0.0", port=port, debug=True)
