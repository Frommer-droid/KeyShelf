import base64
import hashlib
import json
import ssl
import urllib.request

from app.services.vault import Vault
from app.services.wifi_sync import SyncIdentity, SyncServer


def test_desktop_only_save_publishes_immutable_batch_and_shows_database(
    qtapp, tmp_path, monkeypatch
):
    import app.ui.wifi_sync as module
    from app.core.settings import Settings
    from app.ui.main_window import MainWindow
    from app.ui.wifi_sync import Request

    monkeypatch.setattr(module, "ROOT", tmp_path)
    window = MainWindow(Settings(tmp_path / "settings.json"))
    vault, state = Vault.create(tmp_path / "Named database.kdbx", "synthetic-master-123")
    window.opened((vault, state))

    class Server:
        notices = 0

        def notify(self):
            self.notices += 1

        def close(self):
            pass

    server = Server()
    window.wifi_sync.server = server

    def request(base=None, local="b" * 64):
        req = Request("/sync", {"protocol": 3, "hash": local, "base": base, "outgoing": ""})
        window.wifi_sync.handle(req)
        assert req.response[0] == 200
        return req.response[1]

    try:
        assert not window.save_button.isEnabled()
        assert str(vault.path) in window.database_label.text()
        window.saved(vault.service("First local change"))
        window.saved(vault.service("Second local change"))
        assert window.save_button.isEnabled()
        before_save = vault.path.read_bytes()
        assert window.grab().save(str(tmp_path / "windows-manual-ui.png"))
        assert request()["action"] == "idle" and "blob" not in request()
        assert server.notices == 0
        window.save_button.click()
        assert server.notices == 1 and not window.save_button.isEnabled()
        response = request()
        assert response["action"] == "pull"
        assert base64.b64decode(response["blob"]) == before_save
        window.saved(vault.service("Unsent third change"))
        assert window.save_button.isEnabled()
        assert base64.b64decode(request()["blob"]) == before_save
        # Receiver acknowledgement does not publish or discard the new local draft.
        assert request(base=hashlib.sha256(before_save).hexdigest())["action"] == "idle"
        assert window.save_button.isEnabled()
        window.save_button.click()
        assert server.notices == 2
        assert base64.b64decode(request()["blob"]) == vault.path.read_bytes()
    finally:
        window.exit_application()


def test_passive_tls_channel_notifies_only_explicit_events_and_replaces_old_subscriber(tmp_path):
    identity = SyncIdentity(tmp_path)
    seen_requests = []
    server = SyncServer(
        identity, lambda path, body: (seen_requests.append(path) or 200, {}), "127.0.0.1", 0, True
    )
    context = ssl.create_default_context(cadata=identity.data["certificate"])
    context.check_hostname = False
    invitation = identity.invitation("192.168.1.1", server.port)
    token = identity.pair(invitation["invite"])

    def subscribe():
        req = urllib.request.Request(
            f"https://127.0.0.1:{server.port}/events",
            json.dumps({"protocol": 3}).encode(),
            {"Content-Type": "application/json", "Authorization": "Bearer " + token},
        )
        return urllib.request.urlopen(req, context=context, timeout=3)

    first = second = None
    try:
        first = subscribe()
        assert json.loads(first.readline())["event"] == "ready"
        assert server.revision == 0 and seen_requests == []
        server.notify()
        assert json.loads(first.readline())["event"] == "changed"
        second = subscribe()
        assert json.loads(second.readline())["event"] == "ready"
        assert json.loads(second.readline())["event"] == "changed"
        assert first.readline() == b""
        server.notify()
        assert json.loads(second.readline())["event"] == "changed"
        assert seen_requests == []  # no periodic /sync requests
    finally:
        server.close()
        if first:
            first.close()
        if second:
            second.close()
