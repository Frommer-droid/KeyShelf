"""Живой запуск корневой точки входа с временными синтетическими данными."""
import runpy
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app.core.application as lifecycle
from app.core.models import Account, Field
from app.core.settings import ROOT, Settings
from app.services.vault import Vault
from app.ui.main_window import MainWindow
from app.ui.record_dialog import RecordDialog
from tests.native_capture import capture_window


def main():
    screenshot = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "docs" / "vault-cards.png"
    failures = []
    with tempfile.TemporaryDirectory(prefix="secret-vault-smoke-") as directory, ExitStack() as cleanup:
        folder = Path(directory)
        vault, _ = Vault.create(folder / "synthetic.kdbx", "synthetic-live-passphrase-123")
        cleanup.callback(vault.close)
        state = vault.service("OpenAI")
        openai = next(s for s in state.services if s.name == "OpenAI")
        for account in [
            Account(service_id=openai.id, title="Рабочий API", kind="api", favorite=True, api_paid=True,
                    notes="Ключ для рабочего проекта", fields=[Field("API-ключ", "synthetic-main-key")]),
            Account(service_id=openai.id, title="work@example.invalid", login="work@example.invalid", kind="account",
                    fields=[Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "JBSWY3DPEHPK3PXP")]),
            Account(service_id=openai.id, title="personal@example.invalid", login="personal@example.invalid", kind="account",
                    fields=[Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "")]),
            Account(service_id=openai.id, title="Дополнительные данные", kind="other", notes="Демонстрационный комментарий",
                    fields=[Field(f"Поле {i}", f"Вымышленное значение {i}") for i in range(1, 4)]),
        ]:
            state = vault.account(account)
        state = vault.service("Google")
        state = vault.service("Timeweb")

        class SmokeWindow(MainWindow):
            def __init__(self):
                super().__init__(Settings(folder / "settings.json"))
                self.opened((vault, state))
                self.resize(1140, 820)
                QTimer.singleShot(700, self.capture)

            def capture(self):
                try:
                    assert len(self.cards) == 4
                    vault_before = self.vault
                    self.close()
                    assert not self.isVisible() and self.vault is vault_before
                    self.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
                    assert self.isVisible() and self.vault is vault_before
                    card = self.cards[0]
                    card.expand.click()
                    assert card.body.isVisible()
                    next(c for c in self.cards if hasattr(c, "totp")).expand.click()
                    next(c for c in self.cards if c.account.kind == "other").expand.click()
                    self.copy_value("synthetic-live-copy")
                    assert self.clipboard.clipboard.text() == "synthetic-live-copy"
                    self.clipboard.clear_owned()
                    self.status.setText("Демонстрационные данные · все значения вымышленные")
                    QTimer.singleShot(350, self.save_capture)
                except Exception as error:
                    failures.append(type(error).__name__)
                    self.exit_application()

            def save_capture(self):
                try:
                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                    assert self.grab().save(str(screenshot), "PNG")
                    assert capture_window(int(self.winId()), screenshot.with_name("vault-cards-native.png"))
                    self.vault_tab.filter_api.setChecked(True)
                    self.vault_tab.filter_account.setChecked(True)
                    assert len(self.cards) == 3
                    for card in self.cards:
                        if card.account.favorite or hasattr(card, "totp"):
                            card.expand.click()
                    QApplication.processEvents()
                    assert self.grab().save(str(screenshot.with_name("type-filters-active.png")), "PNG")
                    for kind in ("api", "account", "other"):
                        account = next(a for a in self.snapshot.accounts if a.kind == kind)
                        dialog = RecordDialog(self, self.snapshot.services, account)
                        dialog.show()
                        QApplication.processEvents()
                        assert dialog.grab().save(str(screenshot.with_name(f"{kind}-editor.png")), "PNG")
                        dialog.scrub()
                        dialog.close()
                        dialog.deleteLater()
                    self.vault_tab.search.setText("synthetic-main-key")
                    assert not self.cards
                    self.lock()
                    assert not self.snapshot.accounts
                    assert self.stack.currentIndex() == 0
                    assert self.recent_vaults.count() == 1
                    QApplication.processEvents()
                    assert self.grab().save(str(screenshot.with_name("recent-vaults.png")), "PNG")
                    self.tabs.setCurrentIndex(1)
                    QApplication.processEvents()
                    assert self.grab().save(str(screenshot.with_name("system.png")), "PNG")
                except Exception as error:
                    failures.append(type(error).__name__)
                finally:
                    self.exit_application()

        lifecycle.MainWindow = SmokeWindow
        try:
            runpy.run_path(str(ROOT / "Acc-storage.py"), run_name="__main__")
        except SystemExit as exit_status:
            if exit_status.code:
                failures.append(f"exit={exit_status.code}")
        finally:
            vault.close()
        if failures:
            raise RuntimeError("Live smoke failed: " + ", ".join(failures))
    print(f"Live launcher smoke OK; interpreter={sys.executable}; screenshot={screenshot}")


if __name__ == "__main__":
    main()
