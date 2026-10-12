import pytest
from PySide6.QtWidgets import QMessageBox

from app.core.settings import Settings
from app.services.password_access import PasswordAccess
from app.services.vault import Vault, VaultError, VaultPasswordError
from app.ui.main_window import MainWindow
from tests.test_ui import make_window, process


def test_global_mode_protected_roundtrip_and_enable_forgets_all(tmp_path):
    path = tmp_path / "access.dpapi"
    access = PasswordAccess(path)
    first, second = tmp_path / "first.kdbx", tmp_path / "second.kdbx"
    assert access.required and access.password(first) is None
    access.set_required(False, first, "synthetic-first-password")
    access.remember(second, "synthetic-second-password")
    assert b"synthetic-first-password" not in path.read_bytes()
    restored = PasswordAccess(path)
    assert not restored.required
    assert restored.password(first) == "synthetic-first-password"
    assert restored.password(second) == "synthetic-second-password"
    restored.set_required(True)
    required = PasswordAccess(path)
    assert required.required and required.password(first) is None and required.password(second) is None
    path.write_bytes(b"corrupt fixture")
    assert PasswordAccess(path).required


def test_file_lock_keeps_key_and_wrong_password_forgets_only_failed_key(qtapp, tmp_path):
    vault, _ = Vault.create(tmp_path / "test.kdbx", "synthetic-master-123")
    window = MainWindow(Settings(tmp_path / "settings.json"))
    access = window.password_access
    access.set_required(False, vault.path, "synthetic-master-123")
    other = tmp_path / "other.kdbx"
    access.remember(other, "synthetic-other-123")
    try:
        with pytest.raises(VaultError):
            window.open_remembered(vault.path, "synthetic-master-123")
        assert access.password(vault.path) == "synthetic-master-123"
        vault.close()
        with pytest.raises(VaultPasswordError):
            window.open_remembered(vault.path, "synthetic-wrong-123")
        assert access.password(vault.path) is None
        assert access.password(other) == "synthetic-other-123"
    finally:
        vault.close()
        window.exit_application()


def test_restart_and_unlock_without_dialog_then_password_required(qtapp, tmp_path, monkeypatch):
    first = make_window(qtapp, tmp_path)
    settings_path, vault_path = first.settings.path, first.path
    first.system_tab.master_password.setChecked(False)
    assert not first.password_access.required
    first.exit_application()
    # Any unexpected prompt during auto-open is a regression.
    monkeypatch.setattr("app.ui.main_window.PasswordDialog", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected prompt")))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: (_ for _ in ()).throw(AssertionError("unexpected failure")))
    restarted = MainWindow(Settings(settings_path))
    try:
        process(qtapp, lambda: restarted.vault is not None and not restarted.busy)
        assert restarted.path == vault_path
        restarted.lock()
        assert restarted.vault is None
        restarted.unlock()
        process(qtapp, lambda: restarted.vault is not None and not restarted.busy)
        restarted.system_tab.master_password.setChecked(True)
        assert restarted.password_access.required
    finally:
        restarted.exit_application()
    protected = MainWindow(Settings(settings_path))
    try:
        qtapp.processEvents()
        assert protected.vault is None and not protected.busy
        assert protected.system_tab.master_password.isChecked()
    finally:
        protected.exit_application()
