import base64
import hashlib
import json
import ssl
import threading
import time
import urllib.error
import urllib.request

import pytest

from app.services.vault import Vault, VaultError
from app.services.wifi_sync import (
    SyncIdentity,
    SyncServer,
    local_addresses,
    local_ipv4,
    physical_addresses,
    preferred_address,
    sync_action,
    sync_response,
)


def test_physical_lan_addresses_and_last_choice(monkeypatch):
    rows = [{"address": "10.0.0.5", "wifi": False},
            {"address": "192.168.1.7", "wifi": True},
            {"address": "127.0.0.1", "wifi": True},
            {"address": "169.254.1.1", "wifi": False},
            {"address": "8.8.8.8", "wifi": True}]
    addresses = physical_addresses(rows)
    assert addresses == ["192.168.1.7", "10.0.0.5"]
    assert preferred_address(addresses, "10.0.0.5") == "10.0.0.5"
    assert preferred_address(addresses, "172.18.1.1") == "192.168.1.7"
    assert preferred_address([]) is None

    def run(args, **kwargs):
        assert "Get-NetAdapter -Physical" in args[-1]
        assert "Status -eq 'Up'" in args[-1]
        assert kwargs["creationflags"] != 0
        from types import SimpleNamespace
        return SimpleNamespace(stdout=json.dumps(rows).encode())
    monkeypatch.setattr("app.services.wifi_sync.subprocess.run", run)
    assert local_addresses() == addresses


@pytest.mark.parametrize("base,local,remote,action", [
    (None, "", "r", "pull"), (None, "l", "r", "conflict"),
    ("b", "b", "r", "pull"), ("b", "l", "b", "push"),
    ("b", "l", "r", "conflict"), (None, "r", "r", "same"),
])
def test_decisions(base, local, remote, action):
    assert sync_action(base, local, remote) == action


@pytest.mark.parametrize("address,allowed", [
    ("192.168.1.7", True), ("10.0.0.5", True), ("172.31.5.6", True),
    ("127.0.0.1", False), ("8.8.8.8", False), ("172.32.0.1", False),
    ("169.254.1.1", False), ("::1", False),
])
def test_only_lan(address, allowed):
    assert local_ipv4(address) is allowed


def test_response_contains_only_encrypted_blob():
    raw = b"encrypted KDBX fixture"
    result = sync_response(raw, {"base": None, "hash": ""})
    assert base64.b64decode(result["blob"]) == raw
    assert result["hash"] == hashlib.sha256(raw).hexdigest()


def test_tls_one_time_pairing_and_revocation(tmp_path):
    identity = SyncIdentity(tmp_path)
    server = SyncServer(identity, lambda *_: (200, {"action": "same"}), "127.0.0.1", 0, True)
    context = ssl.create_default_context(cadata=identity.data["certificate"])
    context.check_hostname = False

    def request(path, body, token=""):
        request = urllib.request.Request(f"https://127.0.0.1:{server.port}{path}",
            json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, context=context, timeout=3) as response:
            return json.load(response)

    try:
        invite = identity.invitation("192.168.1.1", server.port)
        token = request("/pair", {"invite": invite["invite"]})["token"]
        assert request("/sync", {}, token)["action"] == "same"
        with pytest.raises(urllib.error.HTTPError) as reused:
            request("/pair", {"invite": invite["invite"]})
        assert reused.value.code == 401
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            request("/sync", {}, "wrong-token")
        assert unauthorized.value.code == 401
        assert token.encode() not in identity.path.read_bytes()
        restored = SyncIdentity(tmp_path)
        assert restored.pin == identity.pin
        assert restored.authorized("Bearer " + token)
        identity.revoke()
        with pytest.raises(urllib.error.HTTPError) as revoked:
            request("/sync", {}, token)
        assert revoked.value.code == 401
        invite = identity.invitation("192.168.1.1", server.port)
        identity.expires = int(time.time()) - 1
        assert identity.pair(invite["invite"]) is None
        assert not identity.authorized("Bearer unknown")
    finally:
        server.close()


def test_replace_verifies_and_preserves_backup(tmp_path):
    path = tmp_path / "base.kdbx"
    vault, _ = Vault.create(path, "synthetic-master-123")
    original = path.read_bytes()
    expected = vault.digest.hex()
    with pytest.raises(VaultError):
        vault.replace_from_sync(b"broken", expected)
    assert path.read_bytes() == original
    assert not path.with_suffix(".kdbx.bak").exists()
    vault.service("After mobile sync")
    incoming = path.read_bytes()
    vault.close()
    path.write_bytes(original)
    vault, _ = Vault.open(path, "synthetic-master-123")
    try:
        result = vault.replace_from_sync(incoming, expected)
        assert result.services[0].name == "After mobile sync"
        assert PathBackup(path).read_bytes() == original
        assert vault.digest == hashlib.sha256(incoming).digest()
        with pytest.raises(VaultError):
            vault.replace_from_sync(original, expected)
        assert path.read_bytes() == incoming
    finally:
        vault.close()


def PathBackup(path):
    return path.with_suffix(".kdbx.bak")


def test_qt_dispatch_stages_then_confirms_mobile_file_and_refreshes_ui(qtapp, tmp_path, monkeypatch):
    import app.ui.wifi_sync as sync_ui
    from app.core.settings import Settings
    from app.ui.main_window import MainWindow
    from tests.test_ui import process

    monkeypatch.setattr(sync_ui, "ROOT", tmp_path)
    window = MainWindow(Settings(tmp_path / "settings.json"))
    vault, _ = Vault.create(tmp_path / "qt-base.kdbx", "synthetic-master-123")
    state = vault.service("Original")
    window.opened((vault, state))
    original = vault.path.read_bytes()
    previous_backup = PathBackup(vault.path).read_bytes()
    decoded = Vault.decode(original, "synthetic-master-123")
    decoded.add_group(decoded.root_group, "Added by mobile")
    import io
    buffer = io.BytesIO()
    decoded.save(buffer)
    incoming = buffer.getvalue()

    class FakeServer:
        def notify(self):
            pass

        def close(self):
            pass

    window.wifi_sync.server = FakeServer()
    replies = []
    worker = threading.Thread(target=lambda: replies.append(window.wifi_sync.dispatch("/upload", {
        "protocol": 3, "expected": hashlib.sha256(original).hexdigest(), "blob": base64.b64encode(incoming).decode()})))
    worker.start()
    try:
        process(qtapp, lambda: bool(replies), timeout=15)
        worker.join(timeout=1)
        assert replies[0] == (200, {"protocol": 3, "action": "pending", "hash": hashlib.sha256(incoming).hexdigest()})
        assert vault.path.read_bytes() == original
        assert PathBackup(vault.path).read_bytes() == previous_backup
        dialog = window.wifi_sync.review_dialog
        assert dialog is not None
        next(b for b in dialog.buttons() if b.text() == "Принять").click()
        assert vault.path.read_bytes() == original
        poll = sync_ui.Request("/sync", {"protocol": 3, "base": hashlib.sha256(original).hexdigest(),
                                       "outgoing": hashlib.sha256(incoming).hexdigest(), "hash": hashlib.sha256(incoming).hexdigest()})
        window.wifi_sync.handle(poll)
        process(qtapp, lambda: poll.ready.is_set(), timeout=15)
        assert poll.response[1]["action"] == "ack"
        assert any(s.name == "Added by mobile" for s in window.snapshot.services)
        assert PathBackup(vault.path).read_bytes() == original
        assert not window.busy
        window.lock()
        assert window.wifi_sync.server is None
        assert window.vault is None
    finally:
        window.exit_application()
