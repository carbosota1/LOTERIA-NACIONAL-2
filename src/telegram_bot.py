import os
import requests

def send_telegram_message(text: str, token: str, chat_id: str, timeout: int = 30) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()

def get_telegram_creds(token_env="TELEGRAM_BOT_TOKEN", chat_env="TELEGRAM_CHAT_ID"):
    token = os.getenv(token_env, "").strip()
    chat_id = os.getenv(chat_env, "").strip()
    if not token or not chat_id:
        raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en variables de entorno.")
    return token, chat_id
