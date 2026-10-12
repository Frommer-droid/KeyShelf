from PySide6.QtWidgets import QSystemTrayIcon

from app.services.vault import Vault
from tests.test_ui import make_window, process


def test_close_to_tray_restore_and_exit(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    vault = window.vault
    try:
        assert QSystemTrayIcon.isSystemTrayAvailable()
        assert window.tray.isVisible()
        original = window.snapshot
        window.close()
        assert not window.isVisible()
        assert window.vault is vault and vault.password
        assert window.snapshot is original
        assert window.vault is vault
        window.tray.activate(QSystemTrayIcon.ActivationReason.Trigger)
        assert window.isVisible()
        assert window.vault is vault
        assert not window.in_tray
        window.showMinimized()
        window.tray.open_action.trigger()
        assert window.isVisible() and not window.isMinimized()
        window.tray.exit_action.trigger()
        assert not window.vault and not vault.password
        assert not window.tray.isVisible()
        reopened, state = Vault.open(window.path, "synthetic-test-passphrase-123")
        assert state == original
        reopened.close()
    finally:
        window.exit_application()


def test_tray_exit_finishes_active_save(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    vault = window.vault
    try:
        window.run_job(lambda: vault.service("Saved on exit"), window.saved)
        window.close()
        assert not window.isVisible() and window.vault is vault
        window.tray.exit_action.trigger()
        assert window.closing and not window.vault
        process(qtapp, lambda: not window.busy)
        assert not vault.password and not window.tray.isVisible()
        reopened, state = Vault.open(window.path, "synthetic-test-passphrase-123")
        assert any(s.name == "Saved on exit" for s in state.services)
        reopened.close()
    finally:
        window.exit_application()
