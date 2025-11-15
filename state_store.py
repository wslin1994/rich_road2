# -*- coding: utf-8 -*-
import json, os, time
from typing import Any, Dict

class StateStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"positions":{}, "equity":None, "last_bar_ts":None, "service_id":None}

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def set(self, key: str, value: Any):
        self.state[key] = value
        self.save()

    def get(self, key: str, default=None):
        return self.state.get(key, default)
