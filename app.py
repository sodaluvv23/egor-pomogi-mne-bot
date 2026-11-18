
import os
import re
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


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
            f"Connection error: {type(error).__name__}"
        ) from None

    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram error"))

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


def setup_webhook():
    if not BASE_URL:
        print("Missing Render URL")
        return

    try:
        telegram("setWebhook", {
            "url": f"{BASE_URL}/webhook/{WEBHOOK_SECRET}",
            "secret_token": WEBHOOK_SECRET
        })
        print("Webhook configured")
    except Exception as error:
        print(f"Webhook setup failed: {error}")


@app.route("/")
def home():
    return "Бот работает."


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

    # Запуск бота владельцем
    if user_id == ADMIN_ID and text.startswith("/start"):
        safe_send(
            chat_id,
            "Бот запущен. Все новые обращения будут приходить сюда."
        )
        return "OK", 200

    # Запуск бота пользователем
    if text.startswith("/start"):
        safe_send(
            chat_id,
            "Привет.\n\n"
            "Это личный бот Егора.\n\n"
            "Можешь написать сюда о том, что тебя беспокоит, "
            "рассказать о своей ситуации или просто поговорить.\n\n"
            "Егор прочитает сообщение и ответит, когда сможет.\n\n"
            "Твои сообщения увидит Егор. Не отправляй пароли "
            "и другие секретные данные.\n\n"
            "Если тебе угрожает непосредственная опасность, "
            "обратись в экстренную службу или к человеку, "
            "которому доверяешь."
        )
        return "OK", 200

    # Ответ Егора пользователю
    if user_id == ADMIN_ID:
        replied = message.get("reply_to_message")

        if replied and text:
            original = replied.get("text", "")
            match = re.search(
                r"^ID: (\d+)$",
                original,
                re.MULTILINE
            )

            if match:
                target_id = int(match.group(1))
                safe_send(target_id, text)

        return "OK", 200

    # Игнорируем команды
    if text.startswith("/"):
        return "OK", 200

    # Получаем обращение
    if text:
        name = sender.get("first_name", "Без имени")
        username = sender.get("username")

        username_text = f"@{username}" if username else "не указан"

        report = (
            f"ID: {user_id}\n"
            f"Имя: {name}\n"
            f"Username: {username_text}\n"
            "--------------------\n\n"
            f"{text}"
        )

        result = safe_send(ADMIN_ID, report)

        if not result:
            safe_send(
                chat_id,
                "Не удалось доставить сообщение. Попробуй позже."
            )

    else:
        safe_send(
            chat_id,
            "Пока можно отправлять только текстовые сообщения."
        )

    return "OK", 200


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
