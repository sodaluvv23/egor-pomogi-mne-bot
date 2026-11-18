
import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup

    return requests.post(
        f"{API}/sendMessage",
        json=data,
        timeout=20
    )


@app.route("/")
def home():
    return "Егор, помоги мне! — бот работает."


@app.route("/webhook/" + os.environ.get("WEBHOOK_SECRET", ""))
def webhook():
    return "OK"


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    if request.args.get("secret") != WEBHOOK_SECRET:
        return "Forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message")

    if not message:
        return "OK"

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")

    # Приветствие
    if text == "/start":
        send_message(
            chat_id,
            "Привет! ❤️\n\n"
            "Это бот «Егор, помоги мне!».\n"
            "Здесь ты можешь поделиться тем, "
            "что тебя тревожит, рассказать о проблеме "
            "или просто поговорить.\n\n"
            "Твоё сообщение прочитает Егор и постарается "
            "тебя поддержать.\n\n"
            "Важно: это не профессиональная психологическая "
            "и не экстренная помощь. Если тебе или кому-то "
            "грозит непосредственная опасность, обратись "
            "в местную экстренную службу или к человеку, "
            "которому доверяешь.\n\n"
            "Отправляя сообщение, учитывай, что его прочитает "
            "Егор. Не отправляй пароли и другие секретные данные.\n\n"
            "Можешь написать свою историю прямо сюда."
        )
        return "OK"

    # Команда отмены
    if text == "/cancel":
        send_message(chat_id, "Хорошо. Если захочешь поговорить — я здесь ❤️")
        return "OK"

    # Сообщение от владельца: отвечаем пользователю
    if user_id == ADMIN_ID:
        replied = message.get("reply_to_message")

        if replied:
            original_text = replied.get("text", "")
            for line in original_text.splitlines():
                if line.startswith("ID: "):
                    target_id = int(line.replace("ID: ", "").strip())
                    answer = text

                    if answer:
                        send_message(target_id, "Егор отвечает:\n\n" + answer)
                        send_message(ADMIN_ID, "Ответ отправлен ❤️")
                    return "OK"

        return "OK"

    # Сообщение от пользователя: отправляем владельцу
    if text:
        username = message["from"].get("username")
        name = message["from"].get("first_name", "Без имени")

        info = (
            "📩 НОВОЕ ОБРАЩЕНИЕ\n"
            f"Имя: {name}\n"
            f"Username: @{username if username else 'не указан'}\n"
            f"ID: {user_id}\n\n"
            f"{text}"
        )

        send_message(ADMIN_ID, info)
        send_message(chat_id, "Твоё сообщение отправлено Егору ❤️")

    else:
        send_message(
            chat_id,
            "Пока я принимаю только текстовые сообщения. "
            "Голосовые и фотографии добавим следующим этапом."
        )

    return "OK"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
