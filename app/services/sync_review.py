"""Encrypted proposals and guarded mirroring after a user's answer."""

import hashlib
import json
import os
from pathlib import Path

from app.services.vault import VaultError, fingerprint, snapshot


class SyncReview:
    def __init__(self, root, vault):
        self.vault = vault
        scope = hashlib.sha256(str(vault.path.resolve()).encode()).hexdigest()
        self.root = Path(root) / scope
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "review.json"
        self.state = json.loads(self.path.read_text("utf-8")) if self.path.exists() else {}

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), encoding="utf-8")
        os.replace(temp, self.path)

    def offer(self, raw, expected, modified=0):
        if not isinstance(modified, int) or not 0 <= modified <= 32503680000000:
            raise VaultError("Некорректное время изменения базы.")
        if len(raw) > 32 * 1024 * 1024 or fingerprint(self.vault.path).hex() != expected:
            raise VaultError("База изменилась. Повторите проверку синхронизации.")
        snapshot(self.vault.decode(raw, self.vault.password))
        remote = hashlib.sha256(raw).hexdigest()
        key = expected + ":" + remote
        target = self.root / (remote + ".kdbx")
        if not target.exists():
            temp = target.with_suffix(".tmp")
            temp.write_bytes(raw)
            os.replace(temp, target)
        if self.state.get("key") != key:
            self.state = {
                "key": key,
                "expected": expected,
                "remote": remote,
                "modified": modified,
                "decision": "",
            }
            self.save()

    @property
    def active(self):
        return bool(self.state) and fingerprint(self.vault.path).hex() == self.state.get("expected")

    def preserve(self):
        if not self.active or self.vault.digest.hex() != self.state["expected"]:
            raise VaultError("База изменилась. Повторите проверку синхронизации.")
        target = self.root / (self.state["expected"] + ".kdbx")
        if not target.exists():
            target.write_bytes(self.vault.path.read_bytes())

    def apply(self):
        self.preserve()
        raw = (self.root / (self.state["remote"] + ".kdbx")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.state["remote"]:
            raise VaultError("Ожидающая версия повреждена. Повторите обмен.")
        return self.vault.replace_from_sync(raw, self.state["expected"])

    def accept_phone(self):
        self.preserve()
        self.state["decision"] = "accept_phone"
        self.save()

    def reject_phone(self):
        self.preserve()
        self.state["decision"] = "restore_phone"
        self.save()
