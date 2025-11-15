# -*- coding: utf-8 -*-
import time, json, requests

class Notifier:
    def __init__(self, enabled: bool, bot_token: str, chat_id: str):
        self.enabled = enabled
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.last_err_text = None
        self.last_err_ts = 0

    def _send(self, text: str):
        if not self.enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass

    def info(self, title: str, data: dict=None):
        if data is None: data = {}
        msg = f"✅ <b>{title}</b>\n" + "\n".join([f"{k}: {v}" for k,v in data.items()])
        self._send(msg)

    def warn(self, title: str, data: dict=None):
        if data is None: data = {}
        msg = f"⚠️ <b>{title}</b>\n" + "\n".join([f"{k}: {v}" for k,v in data.items()])
        self._send(msg)

    def error_throttle(self, title: str, data: dict=None, min_interval_sec: int=300):
        if data is None: data = {}
        text = f"{title}|{json.dumps(data, ensure_ascii=False, sort_keys=True)}"
        now = int(time.time())
        if self.last_err_text == text and (now - self.last_err_ts) < min_interval_sec:
            return
        self.last_err_text = text
        self.last_err_ts = now
        msg = f"🛑 <b>{title}</b>\n" + "\n".join([f"{k}: {v}" for k,v in data.items()])
        self._send(msg)
