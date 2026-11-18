
import os
import re
import hmac
import json
import time
import sqlite3
import hashlib
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, render_template, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_PATH = os.environ.get("DB_PATH", "messages.db")


# -----------------------------
# DATABASE
# -----------------------------

def get_db():
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_replies (
                admin_message_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        """)


def save_message(user_id, role, text):
    with get_db() as db:
        db.execute(
            """
            INSERT INTO messages (user_id, role, text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, role, text, int(time.time()))
        )


def save_reply_link(admin_message_id, user_id):
    with get_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO admin_replies
            (admin_message_id, user_id)
            VALUES (?, ?)
            """,
            (admin_message_id, user_id)
        )


def find_reply_user(admin_message_id):
    with get_db() as db:
        result = db.execute(
            """
            SELECT user_id FROM admin_replies
            WHERE admin_message_id = ?
            """,
            (admin_message_id,)
        ).fetchone()

    return result["user_id"] if result else None


def get_user_replies(user_id, after_id=0):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, text, created_at
            FROM messages
            WHERE user_id = ?
              AND role = 'admin'
              AND id > ?
            ORDER BY id ASC
            LIMIT 100
            """,
            (user_id, after_id)
        ).fetchall()

    return [dict(row) for row in rows]


# -----------------------------
# TELEGRAM API
# -----------------------------

def telegram(method, data):
    try:
        response = requests.post(
            f"{API}/{method}",
            json=data,
            timeout=20
        )
        result = response.json()
    except Exception as error:
        raise RuntimeError(
            f"Telegram connection error: {type(error).__name__}"
        ) from None

    if not result.get("ok"):
        raise RuntimeError(
            result.get("description", "Telegram API error")
        )

    return result


def send_message(chat_id, text):
    return telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text
    })


def safe_send(chat_id, text):
    try:
        return send_message(chat_id, text)
    except Exception as error:
        print(f"Message delivery failed: {error}")
        return None


# -----------------------------
# TELEGRAM MINI APP AUTH
# -----------------------------

def validate_init_data(init_data):
    if not init_data:
        return None

    try:
        parsed = dict(parse_qsl(
            init_data,
            keep_blank_values=True
        ))

        received_hash = parsed.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        auth_date = int(parsed.get("auth_date", "0"))

        if time.time() - auth_date > 86400:
            return None

        user_data = json.loads(parsed.get("user", "{}"))
        user_id = user_data.get("id")

        if not user_id:
            return None

        return int(user_id)

    except Exception:
        return None


# -----------------------------
# WEBHOOK
# -----------------------------

def setup_webhook():
    if not BASE_URL:
        print("Render URL is missing")
        return

    try:
        telegram("setWebhook", {
            "url": f"{BASE_URL}/webhook/{WEBHOOK_SECRET}",
            "secret_token": WEBHOOK_SECRET
        })

        telegram("setChatMenuButton", {
            "menu_button": {
                "type": "web_app",
                "text": "Открыть приложение ❤️",
                "web_app": {
                    "url": BASE_URL
                }
            }
        })

        print("Webhook and Mini App menu configured")

    except Exception as error:
        print(f"Telegram setup failed: {error}")


# -----------------------------
# WEBSITE
# -----------------------------

@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------
# MINI APP: SEND MESSAGE
# -----------------------------

@app.route("/api/message", methods=["POST"])
def api_message():
    data = request.get_json(silent=True) or {}

    user_id = validate_init_data(
        data.get("initData", "")
    )

    if not user_id:
        return jsonify({
            "ok": False,
            "error": "Не удалось проверить Telegram. Открой приложение через бота."
        }), 401

    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({
            "ok": False,
            "error": "Пустое сообщение"
        }), 400

    if len(text) > 4000:
        return jsonify({
            "ok": False,
            "error": "Сообщение слишком длинное"
        }), 400

    save_message(user_id, "user", text)

    report = (
        "📩 НОВОЕ ОБРАЩЕНИЕ ИЗ MINI APP\n\n"
        f"🆔 ID: {user_id}\n"
        "━━━━━━━━━━━━━━\n\n"
        f"{text}"
    )

    result = safe_send(ADMIN_ID, report)

    if not result:
        return jsonify({
            "ok": False,
            "error": "Не удалось доставить сообщение. Попробуй позже."
        }), 503

    admin_message_id = result["result"]["message_id"]

    save_reply_link(admin_message_id, user_id)

    return jsonify({
        "ok": True,
        "message": "Сообщение доставлено Егору ❤️"
    })


# -----------------------------
# MINI APP: GET REPLIES
# -----------------------------

@app.route("/api/messages", methods=["POST"])
def api_messages():
    data = request.get_json(silent=True) or {}

    user_id = validate_init_data(
        data.get("initData", "")
    )

    if not user_id:
        return jsonify({
            "ok": False,
            "error": "Не удалось проверить Telegram"
        }), 401

    try:
        after_id = max(0, int(data.get("after_id", 0)))
    except (TypeError, ValueError):
        after_id = 0

    replies = get_user_replies(user_id, after_id)

    return jsonify({
        "ok": True,
        "messages": replies
    })


# -----------------------------
# TELEGRAM WEBHOOK
# -----------------------------

@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):

    if secret != WEBHOOK_SECRET:
        return "Forbidden", 403

    if request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        return "Forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if not message:
        return "OK", 200

    sender = message.get("from", {})
    user_id = sender.get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or message.get("caption") or ""

    if not user_id or not chat_id:
        return "OK", 200

    # ADMIN START

    if user_id == ADMIN_ID and text.startswith("/start"):
        safe_send(
            chat_id,
            "Привет, Егор! ❤️\n\n"
            "Бот «Егор, помоги мне!» работает.\n"
            "Все новые обращения будут приходить сюда.\n\n"
            "Чтобы ответить человеку, нажми «Ответить» "
            "на его сообщение."
        )
        return "OK", 200

    # USER START

    if text.startswith("/start"):
        safe_send(
            chat_id,
            "Привет! ❤️\n\n"
            "Добро пожаловать в «Егор, помоги мне!».\n\n"
            "Здесь можно рассказать о том, что тебя тревожит, "
            "поделиться переживаниями или просто поговорить.\n\n"
            "Егор прочитает твоё сообщение и постарается поддержать тебя.\n\n"
            "Можешь писать свободно. Твои сообщения увидит Егор.\n\n"
            "Это не профессиональная психологическая и не экстренная "
            "помощь. Если тебе угрожает опасность, обратись "
            "в местную экстренную службу или к близкому человеку."
        )
        return "OK", 200

    # ADMIN REPLY

    if user_id == ADMIN_ID:
        replied = message.get("reply_to_message")

        if replied and text:
            admin_message_id = replied.get("message_id")

            target_id = find_reply_user(admin_message_id)

            # Совместимость со старыми сообщениями
            if not target_id:
                original = (
                    replied.get("text")
                    or replied.get("caption")
                    or ""
                )

                match = re.search(
                    r"^🆔 ID: (\d+)$",
                    original,
                    re.MULTILINE
                )

                if match:
                    target_id = int(match.group(1))

            if target_id:
                result = safe_send(target_id, text)

                if result:
                    save_message(target_id, "admin", text)
                    print(f"Reply delivered to {target_id}")
                else:
                    safe_send(
                        ADMIN_ID,
                        "Не удалось отправить ответ пользователю 😔"
                    )

        return "OK", 200

    # IGNORE COMMANDS

    if text.startswith("/"):
        return "OK", 200

    # ORDINARY TELEGRAM MESSAGE

    if text:
        name = sender.get("first_name", "Без имени")
        username = sender.get("username")
        username_text = f"@{username}" if username else "не указан"

        save_message(user_id, "user", text)

        report = (
            "📩 НОВОЕ ОБРАЩЕНИЕ\n\n"
            f"👤 Имя: {name}\n"
            f"🔗 Username: {username_text}\n"
            f"🆔 ID: {user_id}\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{text}"
        )

        result = safe_send(ADMIN_ID, report)

        if result:
            save_reply_link(
                result["result"]["message_id"],
                user_id
            )

            safe_send(
                chat_id,
                "Твоё сообщение доставлено Егору ❤️\n\n"
                "Он увидит его и ответит, когда сможет."
            )
        else:
            safe_send(
                chat_id,
                "Не удалось доставить сообщение Егору 😔\n"
                "Попробуй немного позже."
            )

    else:
        safe_send(
            chat_id,
            "Пока бот принимает только текстовые сообщения ❤️"
        )

    return "OK", 200


# -----------------------------
# START
# -----------------------------

init_db()
setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
