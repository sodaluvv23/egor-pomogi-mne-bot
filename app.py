
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
            f"Telegram connection error: {type(error).__name__}"
        ) from None

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result.get('description', 'Unknown error')}"
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


def setup_webhook():
    if not BASE_URL:
        print("RENDER_EXTERNAL_URL is missing")
        return

    try:
        result = telegram("setWebhook", {
            "url": f"{BASE_URL}/webhook/{WEBHOOK_SECRET}",
            "secret_token": WEBHOOK_SECRET
        })
        print("Webhook configured:", result.get("ok"))
    except Exception as error:
        print(f"Webhook setup failed: {error}")


@app.route("/")
def home():
    return "Егор, помоги мне! — бот работает."


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

    # Команда /start от владельца бота
    if user_id == ADMIN_ID and text.startswith("/start"):
        safe_send(
            chat_id,
            "Привет, Егор! ❤️\n\n"
            "Бот «Егор, помоги мне!» запущен.\n"
            "Сюда будут приходить сообщения пользователей.\n\n"
            "Чтобы ответить человеку, нажми «Ответить» "
            "на его сообщении и напиши свой ответ."
        )
        return "OK", 200

    # Команда /start от пользователя
    if text.startswith("/start"):
        safe_send(
            chat_id,
            "Привет! ❤️\n\n"
            "Это бот «Егор, помоги мне!».\n\n"
            "Здесь ты можешь поделиться тем, что тебя тревожит, "
            "рассказать о проблеме или просто поговорить.\n\n"
            "Твоё сообщение прочитает Егор и постарается тебя поддержать.\n\n"
            "Важно: это не профессиональная психологическая "
            "и не экстренная помощь. При непосредственной опасности "
            "обратись в местную экстренную службу или к человеку, "
            "которому доверяешь.\n\n"
            "Сообщения читает Егор. Не отправляй пароли "
            "и другие секретные данные.\n\n"
            "Можешь написать свою историю прямо сюда."
        )
        return "OK", 200

    # Обработка ответов Егора
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

                result = safe_send(
                    target_id,
                    "Егор отвечает:\n\n" + text
                )

                if result:
                    safe_send(ADMIN_ID, "Ответ отправлен ❤️")
                else:
                    safe_send(
                        ADMIN_ID,
                        "Не удалось доставить ответ. "
                        "Возможно, пользователь заблокировал бота."
                    )

        return "OK", 200

    # Не обрабатываем другие команды
    if text.startswith("/"):
        return "OK", 200

    # Пересылка сообщения владельцу
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

        result = safe_send(ADMIN_ID, report)

        if result:
            safe_send(chat_id, "Твоё сообщение отправлено Егору ❤️")
        else:
            safe_send(
                chat_id,
                "Не удалось доставить сообщение. "
                "Попробуй написать немного позже."
            )

    else:
        safe_send(
            chat_id,
            "Пока я принимаю только текстовые сообщения. "
            "Фото и голосовые добавим позже."
        )

    return "OK", 200


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
