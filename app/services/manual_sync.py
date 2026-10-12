"""Explicit immutable publication. Unpublished edits never enter the transport."""

import hashlib
import json
import os
import time
from pathlib import Path

from app.services.vault import VaultError


class ManualOutbox:
    def __init__(self, root, vault):
        self.vault = vault
        scope = hashlib.sha256(str(vault.path.resolve()).encode()).hexdigest()
        self.root = Path(root) / scope
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "state.json"
        self.state = (
            json.loads(self.path.read_text("utf-8"))
            if self.path.exists()
            else {"saved": vault.digest.hex(), "outgoing": "", "modified": 0}
        )
        self.save()

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state), encoding="utf-8")
        os.replace(temp, self.path)

    @property
    def dirty(self):
        return self.vault.digest.hex() != self.state["saved"]

    def publish(self):
        raw = self.vault.path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != self.vault.digest.hex():
            raise VaultError("Файл изменился. Откройте базу заново.")
        if digest == self.state["saved"]:
            return False
        target = self.root / (digest + ".kdbx")
        temp = target.with_suffix(".tmp")
        temp.write_bytes(raw)
        os.replace(temp, target)
        self.state = {"saved": digest, "outgoing": digest, "modified": int(time.time() * 1000)}
        self.save()
        return True

    def payload(self):
        digest = self.state.get("outgoing")
        if not digest:
            return None
        raw = (self.root / (digest + ".kdbx")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise VaultError("Пакет повреждён. Сохраните изменения заново.")
        return raw

    def acknowledge(self, digest):
        if digest == self.state.get("outgoing"):
            self.state["outgoing"] = ""
            self.save()

    def received(self, digest):
        self.state = {"saved": digest, "outgoing": "", "modified": 0}
        self.save()
