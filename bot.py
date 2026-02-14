from flask import Flask, request
import os
import json
import requests
import threading
import time

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
RENDER_URL = os.getenv("RENDER_URL", "")

app = Flask(__name__)

# Хранилище в памяти
user_data = {}

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


def search_web(query):
    try:
        from bs4 import BeautifulSoup
        resp = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
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


def send_msg(chat_id, text, keyboard=None):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    while text:
        chunk = text[:4000]
        text = text[4000:]
        payload = {"chat_id": chat_id, "text": chunk}
        if keyboard and not text:
            payload["reply_markup"] = json.dumps(keyboard)
        try:
            requests.post(url, json=payload, timeout=30)
        except:
            pass


def send_typing(chat_id):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=10)
    except:
        pass


def answer_cb(callback_id, text=""):
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text}, timeout=10)
    except:
        pass


def main_kb():
    return {"inline_keyboard": [
        [{"text": "💬 Помощник", "callback_data": "mode_helper"}, {"text": "📊 Бизнес", "callback_data": "mode_business"}],
        [{"text": "✍️ Контент", "callback_data": "mode_content"}, {"text": "💻 Код", "callback_data": "mode_coder"}],
        [{"text": "📋 Стартап", "callback_data": "mode_startup"}, {"text": "🔍 Исследование", "callback_data": "mode_research"}],
        [{"text": "🚀 Автоматизация", "callback_data": "mode_automate"}, {"text": "📝 Копирайтинг", "callback_data": "mode_copywriter"}],
        [{"text": "🎯 Коуч", "callback_data": "mode_coach"}, {"text": "🌍 Переводчик", "callback_data": "mode_translator"}],
        [{"text": "📦 Шаблоны", "callback_data": "show_templates"}, {"text": "🛠 Инструменты", "callback_data": "show_tools"}],
    ]}


def tpl_kb():
    return {"inline_keyboard": [
        [{"text": "📋 Бизнес-план", "callback_data": "tpl_biz_plan"}],
        [{"text": "📅 Контент-план", "callback_data": "tpl_content_plan"}],
        [{"text": "🔍 Анализ конкурентов", "callback_data": "tpl_competitor"}],
        [{"text": "📄 Резюме", "callback_data": "tpl_resume"}],
        [{"text": "✍️ Пак постов", "callback_data": "tpl_post_pack"}],
        [{"text": "🌐 Текст лендинга", "callback_data": "tpl_landing"}],
        [{"text": "📧 Email-цепочка", "callback_data": "tpl_email_chain"}],
        [{"text": "📊 SWOT-анализ", "callback_data": "tpl_swot"}],
        [{"text": "⬅️ Назад", "callback_data": "back_main"}],
    ]}


def tools_kb():
    return {"inline_keyboard": [
        [{"text": "🔍 Поиск в интернете", "callback_data": "tool_search"}],
        [{"text": "🌐 Спарсить сайт", "callback_data": "tool_parse"}],
        [{"text": "📝 Суммаризация", "callback_data": "tool_summarize"}],
        [{"text": "🇬🇧→🇷🇺 EN→RU", "callback_data": "tool_enru"}],
        [{"text": "🇷🇺→🇬🇧 RU→EN", "callback_data": "tool_ruen"}],
        [{"text": "🗑 Очистить контекст", "callback_data": "tool_clear"}],
        [{"text": "⬅️ Назад", "callback_data": "back_main"}],
    ]}


def after_kb():
    return {"inline_keyboard": [
        [{"text": "🔄 Подробнее", "callback_data": "act_more"}, {"text": "📝 Переписать", "callback_data": "act_rewrite"}],
        [{"text": "📋 Список", "callback_data": "act_list"}, {"text": "🎯 Пример", "callback_data": "act_example"}],
        [{"text": "🏠 Меню", "callback_data": "back_main"}],
    ]}


def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    cb_id = cb["id"]
    data = cb["data"]

    if data.startswith("mode_"):
        mode_key = data[5:]
        if mode_key in MODES:
            set_user(chat_id, "mode", mode_key)
            set_user(chat_id, "context", [])
            set_user(chat_id, "waiting", "")
            m = MODES[mode_key]
            answer_cb(cb_id, m["name"])
            send_msg(chat_id, m["emoji"] + " Режим: " + m["name"] + "\n\nЗадавай вопросы!", after_kb())

    elif data == "show_templates":
        answer_cb(cb_id)
        send_msg(chat_id, "📦 Выбери шаблон:", tpl_kb())

    elif data.startswith("tpl_"):
        key = data[4:]
        if key in TEMPLATES:
            answer_cb(cb_id, TEMPLATES[key]["name"])
            send_typing(chat_id)
            answer = call_ai(get_mode_prompt(chat_id), TEMPLATES[key]["prompt"], get_context(chat_id))
            add_context(chat_id, "user", TEMPLATES[key]["prompt"])
            add_context(chat_id, "assistant", answer)
            send_msg(chat_id, answer, after_kb())

    elif data == "show_tools":
        answer_cb(cb_id)
        send_msg(chat_id, "🛠 Выбери инструмент:", tools_kb())

    elif data == "tool_search":
        answer_cb(cb_id)
        set_user(chat_id, "waiting", "search")
        send_msg(chat_id, "🔍 Напиши запрос:")

    elif data == "tool_parse":
        answer_cb(cb_id)
        set_user(chat_id, "waiting", "parse")
        send_msg(chat_id, "🌐 Отправь ссылку:")

    elif data == "tool_summarize":
        answer_cb(cb_id)
        set_user(chat_id, "waiting", "summarize")
        send_msg(chat_id, "📝 Отправь текст:")

    elif data == "tool_enru":
        answer_cb(cb_id)
        set_user(chat_id, "waiting", "enru")
        send_msg(chat_id, "🇬🇧→🇷🇺 Отправь текст:")

    elif data == "tool_ruen":
        answer_cb(cb_id)
        set_user(chat_id, "waiting", "ruen")
        send_msg(chat_id, "🇷🇺→🇬🇧 Отправь текст:")

    elif data == "tool_clear":
        answer_cb(cb_id, "Очищено!")
        set_user(chat_id, "context", [])
        send_msg(chat_id, "🗑 Очищено!", main_kb())

    elif data == "act_more":
        answer_cb(cb_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Расскажи подробнее. Деталей, цифр, примеров.", get_context(chat_id))
        add_context(chat_id, "user", "Подробнее")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, after_kb())

    elif data == "act_rewrite":
        answer_cb(cb_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Перепиши лучше.", get_context(chat_id))
        add_context(chat_id, "user", "Переписать")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, after_kb())

    elif data == "act_list":
        answer_cb(cb_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Оформи списком.", get_context(chat_id))
        add_context(chat_id, "user", "Списком")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, after_kb())

    elif data == "act_example":
        answer_cb(cb_id)
        send_typing(chat_id)
        answer = call_ai(get_mode_prompt(chat_id), "Дай пример с цифрами.", get_context(chat_id))
        add_context(chat_id, "user", "Пример")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, answer, after_kb())

    elif data == "back_main":
        answer_cb(cb_id)
        mode = get_user(chat_id, "mode", DEFAULT_MODE)
        send_msg(chat_id, "🤖 Jarvis 2.0 | " + MODES.get(mode, MODES[DEFAULT_MODE])["name"], main_kb())


def handle_message(chat_id, text):
    text = text.strip()

    if text in ["/start", "/menu"]:
        send_msg(chat_id, "🤖 Jarvis AI Agent 2.0\n\nВыбери режим или напиши вопрос:", main_kb())
        return

    waiting = get_user(chat_id, "waiting", "")

    if waiting == "search":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        results = search_web(text)
        answer = call_ai(get_mode_prompt(chat_id), "Поиск '" + text + "':\n\n" + results + "\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Поиск: " + text)
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🔍 " + text + "\n\n" + answer, after_kb())
        return

    if waiting == "parse":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        content = parse_website(text)
        answer = call_ai(get_mode_prompt(chat_id), "Сайт " + text + ":\n\n" + content + "\n\nАнализ.", get_context(chat_id))
        add_context(chat_id, "user", "Парсинг: " + text)
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "🌐\n\n" + answer, after_kb())
        return

    if waiting == "summarize":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        answer = call_ai("Суммаризатор на русском.", "5 главных мыслей:\n\n" + text[:3000], [])
        add_context(chat_id, "user", "Суммаризация")
        add_context(chat_id, "assistant", answer)
        send_msg(chat_id, "📝\n\n" + answer, after_kb())
        return

    if waiting == "enru":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        answer = call_ai("Переводчик.", "Переведи на русский:\n\n" + text, [])
        send_msg(chat_id, "🇬🇧→🇷🇺\n\n" + answer, after_kb())
        return

    if waiting == "ruen":
        set_user(chat_id, "waiting", "")
        send_typing(chat_id)
        answer = call_ai("Переводчик.", "Переведи на английский, 2 варианта:\n\n" + text, [])
        send_msg(chat_id, "🇷🇺→🇬🇧\n\n" + answer, after_kb())
        return

    send_typing(chat_id)
    answer = call_ai(get_mode_prompt(chat_id), text, get_context(chat_id))
    add_context(chat_id, "user", text)
    add_context(chat_id, "assistant", answer)
    send_msg(chat_id, answer, after_kb())


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
            send_msg(chat_id, "Ошибка. Попробуй ещё раз.")

    return "ok"


@app.route("/", methods=["GET"])
def home():
    return "Jarvis 2.0 is running!"


def setup_webhook():
    if RENDER_URL:
        webhook_url = RENDER_URL + "/webhook"
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/setWebhook"
        resp = requests.post(url, json={"url": webhook_url}, timeout=10)
        print("Webhook set:", resp.json())


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
    app.run(host="0.0.0.0", port=port)
