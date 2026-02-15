from flask import Flask, request, jsonify, render_template
import os
import json
import requests
import time
import uuid

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

app = Flask(__name__)

# Хранилище сессий
sessions = {}

MODES = {
    "helper": {"name": "💬 Помощник", "prompt": "Ты универсальный AI-помощник Jarvis. Отвечай кратко и по делу на русском.", "emoji": "💬"},
    "business": {"name": "📊 Бизнес", "prompt": "Ты бизнес-аналитик Jarvis. Анализируй рынки, конкурентов, тренды. На русском.", "emoji": "📊"},
    "content": {"name": "✍️ Контент", "prompt": "Ты контент-менеджер Jarvis. Пишешь посты, статьи, рекламу. На русском.", "emoji": "✍️"},
    "coder": {"name": "💻 Код", "prompt": "Ты full-stack разработчик Jarvis. Пишешь чистый код. На русском.", "emoji": "💻"},
    "startup": {"name": "📋 Стартап", "prompt": "Ты стартап-консультант Jarvis. Бизнес-планы, идеи. На русском.", "emoji": "📋"},
    "research": {"name": "🔍 Исследование", "prompt": "Ты исследователь рынка Jarvis. Анализируй ниши, тренды. На русском.", "emoji": "🔍"},
    "automate": {"name": "🚀 Автоматизация", "prompt": "Ты эксперт по автоматизации Jarvis. Скрипты, боты. На русском.", "emoji": "🚀"},
    "copywriter": {"name": "📝 Копирайтинг", "prompt": "Ты копирайтер Jarvis. Продающие тексты. На русском.", "emoji": "📝"},
    "coach": {"name": "🎯 Коуч", "prompt": "Ты лайф-коуч Jarvis. Цели, мотивация. На русском.", "emoji": "🎯"},
    "translator": {"name": "🌍 Переводчик", "prompt": "Ты переводчик Jarvis. Переводишь тексты. На русском.", "emoji": "🌍"},
}


def get_session(sid):
    if sid not in sessions:
        sessions[sid] = {
            "mode": "helper",
            "context": [],
            "messages": []
        }
    return sessions[sid]


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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json()
    sid = data.get("session_id", "")
    text = data.get("text", "").strip()
    if not sid or not text:
        return jsonify({"error": "empty"}), 400

    session = get_session(sid)
    mode = session["mode"]
    prompt = MODES.get(mode, MODES["helper"])["prompt"]

    # Сохраняем сообщение юзера
    session["messages"].append({"role": "user", "text": text, "time": time.strftime("%H:%M")})
    session["context"].append({"role": "user", "text": text[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    # AI ответ
    answer = call_ai(prompt, text, session["context"])

    session["messages"].append({"role": "assistant", "text": answer, "time": time.strftime("%H:%M")})
    session["context"].append({"role": "assistant", "text": answer[:1000]})
    if len(session["context"]) > 20:
        session["context"] = session["context"][-20:]

    return jsonify({"answer": answer, "time": time.strftime("%H:%M")})


@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.get_json()
    sid = data.get("session_id", "")
    mode = data.get("mode", "helper")
    if sid and mode in MODES:
        session = get_session(sid)
        session["mode"] = mode
        session["context"] = []
        return jsonify({"ok": True, "mode": MODES[mode]})
    return jsonify({"error": "invalid"}), 400


@app.route("/api/clear", methods=["POST"])
def api_clear():
    data = request.get_json()
    sid = data.get("session_id", "")
    if sid:
        session = get_session(sid)
        session["context"] = []
        session["messages"] = []
        return jsonify({"ok": True})
    return jsonify({"error": "invalid"}), 400


@app.route("/api/modes", methods=["GET"])
def api_modes():
    return jsonify(MODES)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
