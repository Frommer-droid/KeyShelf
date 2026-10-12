import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QSpinBox

from app.core.settings import Settings
from app.services.vault import Vault
from app.ui.main_window import MainWindow
from tests.test_ui import make_window, process


def test_recent_history_order_limit_and_no_password(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    paths = [tmp_path / f"vault-{i}.kdbx" for i in range(12)]
    for path in paths:
        settings.remember_vault(path)
    assert len(settings.data["recent_vaults"]) == 10
    settings.remember_vault(paths[5])
    restored = Settings(settings.path)
    assert restored.data["recent_vaults"][0] == str(paths[5])
    assert restored.data["recent_vaults"].count(str(paths[5])) == 1
    assert not any(k in restored.data for k in ("password", "idle_minutes", "clipboard_seconds", "reveal_seconds"))
    data = json.loads(settings.path.read_text(encoding="utf-8"))
    assert data["recent_vaults"] == restored.data["recent_vaults"]


def test_recent_list_restart_click_and_missing_file(qtapp, tmp_path, monkeypatch):
    first = make_window(qtapp, tmp_path)
    path = first.path
    settings_path = first.settings.path
    first.exit_application()
    window = MainWindow(Settings(settings_path))
    window.show()
    try:
        assert window.recent_vaults.count() == 1
        item = window.recent_vaults.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == str(path)
        assert item.flags() & Qt.ItemFlag.ItemIsEnabled
        requested = []
        monkeypatch.setattr(window, "request_password", lambda p: requested.append(p))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (_ for _ in ()).throw(AssertionError("File picker must not open")))
        window.recent_vaults.itemClicked.emit(item)
        assert requested == [path]
        path.unlink()
        window.open_recent(item)
        assert requested == [path]
        assert not window.recent_vaults.item(0).flags() & Qt.ItemFlag.ItemIsEnabled
        assert "недоступен" in window.recent_vaults.item(0).text()
        assert not window.system_tab.findChildren(QSpinBox)
        assert not hasattr(window, "idle_timer")
        assert not hasattr(window, "session")
        assert not hasattr(window.clipboard, "timer")
    finally:
        window.exit_application()


def test_failed_open_does_not_enter_history(qtapp, tmp_path, monkeypatch):
    path = tmp_path / "synthetic.kdbx"
    vault, _ = Vault.create(path, "synthetic-password-123")
    vault.close()
    window = MainWindow(Settings(tmp_path / "settings.json"))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(True))
    try:
        window.run_job(lambda: Vault.open(path, "wrong-password"), window.opened)
        process(qtapp, lambda: not window.busy)
        assert errors
        assert not window.settings.data["recent_vaults"]
    finally:
        window.exit_application()
