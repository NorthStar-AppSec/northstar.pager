"""Send one message to the configured Telegram chat."""
import os
import urllib.parse

from .net import http_json


def send(text):
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000]}).encode()
    http_json(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage", data=data)
