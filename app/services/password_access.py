"""Device-local opt-in unlock. KDBX and its password remain unchanged."""
import json
import os
from pathlib import Path

from app.services.wifi_sync import dpapi


class PasswordAccess:
    def __init__(self, path):
        self.path = Path(path)
        self.required = True
        self.passwords = {}
        try:
            state = json.loads(dpapi(self.path.read_bytes(), decrypt=True))
            if isinstance(state, dict) and state.get("required") is False and isinstance(state.get("passwords"), dict):
                self.required = False
                self.passwords = {k: v for k, v in state["passwords"].items()
                                  if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError, TypeError, RuntimeError):
            pass  # Missing or inaccessible device key means password-required.

    @staticmethod
    def key(path):
        return os.path.normcase(str(Path(path).resolve()))

    def password(self, path):
        return None if self.required else self.passwords.get(self.key(path))

    def _save(self, required, passwords):
        raw = json.dumps({"required": required, "passwords": passwords}).encode()
        encrypted = dpapi(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        with temp.open("wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)
        self.required, self.passwords = required, passwords

    def set_required(self, required, path=None, password=None):
        passwords = {} if required else dict(self.passwords)
        if not required and path is not None and password is not None:
            passwords[self.key(path)] = password
        self._save(required, passwords)

    def remember(self, path, password):
        if not self.required:
            passwords = dict(self.passwords)
            passwords[self.key(path)] = password
            self._save(False, passwords)

    def forget(self, path):
        passwords = dict(self.passwords)
        passwords.pop(self.key(path), None)
        self._save(self.required, passwords)
