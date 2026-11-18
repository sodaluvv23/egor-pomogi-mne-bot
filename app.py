
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
    response = requests.post(
        f"{API}/{method}",
        json=data,
        timeout=20
    )
    response.raise_for_status()
    return response.json()


def send_message(chat_id, text):
    return telegram("sendMessage", {
        "chat_id": chat_id,
        "text": text
    })


def setup_webhook():
    if not BASE_URL:
        print("RENDER_EXTERNAL_URL is not set yet")
        return

    result = telegram("setWebhook", {
        "url": f"{BASE_URL}/webhook/{WEBHOOK_SECRET}",
        "secret_token": WEBHOOK_SECRET
    })
    print("Webhook setup:", result)


@app.route("/")
def home():
    return "Егор, помоги мне! — бот работает."


@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        return "Forbidden", 403

    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return "Forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if not message:
        return "OK"

    sender = message.get("from", {})
    user_id = sender.get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not user_id or not chat_id:
        return "OK"

    # Команда запуска
    if text == "/start" and user_id != ADMIN_ID:
        send_message(
            chat_id,
            "Привет! ❤️\n\n"
            "Это бот «Егор, помоги мне!».\n\n"
            "Здесь ты можешь поделиться тем, что тебя тревожит, "
            "рассказать о проблеме или просто поговорить.\n\n"
            "Твоё сообщение прочитает Егор и постарается тебя поддержать.\n\n"
            "Важно: это не профессиональная психологическая и не экстренная "
            "помощь. При непосредственной опасности обратись в местную "
            "экстренную службу или к человеку, которому доверяешь.\n\n"
            "Сообщения читает Егор. Не отправляй пароли и секретные данные.\n\n"
            "Можешь написать свою историю прямо сюда."
        )
        return "OK"

    if user_id == ADMIN_ID:
        replied = message.get("reply_to_message")

        if replied and text:
            original = replied.get("text", "")
            match = re.search(r"^ID: (\d+)$", original, re.MULTILINE)

            if match:
                target_id = int(match.group(1))
                send_message(target_id, "Егор отвечает:\n\n" + text)
                send_message(ADMIN_ID, "Ответ отправлен ❤️")

        return "OK"

    if text.startswith("/"):
        return "OK"

    if text:
        name = sender.get("first_name", "Без имени")
        username = sender.get("username")
        username_text = f"@{username}" if username else "не указан"

        report = (
            "📩 НОВОЕ ОБРАЩЕНИЕ\n"
            f"Имя: {name}\n"
            f"Username: {username_text}\n"
            f"ID: {user_id}\n\n"
            f"{text}"
        )

        send_message(ADMIN_ID, report)
        send_message(chat_id, "Твоё сообщение отправлено Егору ❤️")

    else:
        send_message(
            chat_id,
            "Пока я принимаю только текстовые сообщения. "
            "Фото и голосовые добавим позже."
        )

    return "OK"


setup_webhook()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
