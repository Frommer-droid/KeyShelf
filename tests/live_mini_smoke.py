"""Живой запуск мини-режима через entrypoint с вымышленными данными."""
import json
import logging
import runpy
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QSystemTrayIcon

import app.core.application as lifecycle
from app.core.models import Account, Field
from app.core.settings import ROOT, Settings
from app.services.vault import Vault
from app.ui.main_window import MainWindow
from app.ui.widgets import CopyIconButton


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    original_root = lifecycle.ROOT
    original_window = lifecycle.MainWindow
    with tempfile.TemporaryDirectory(prefix="keyshelf-mini-smoke-") as directory:
        folder = Path(directory)
        lifecycle.ROOT = folder  # Журнал проверки не заменяет пользовательский.
        vault, state = Vault.create(folder / "synthetic.kdbx", "synthetic-mini-passphrase")
        state = vault.service("OpenAI")
        service = state.services[0].id
        state = vault.account(Account(service_id=service, title="Рабочий API", kind="api",
                                      fields=[Field("API-ключ", "synthetic-api-key")]))
        state = vault.service("Второй сервис")
        second = next(s.id for s in state.services if s.id != service)
        state = vault.account(Account(service_id=second, title="Рабочий аккаунт", kind="account",
                                      login="demo@example.invalid",
                                      fields=[Field("Пароль", "synthetic-password"),
                                              Field("Секрет 2FA", "JBSWY3DPEHPK3PXP")]))

        class SmokeWindow(MainWindow):
            def __init__(self):
                super().__init__(Settings(folder / "settings.json"))
                self.opened((vault, state))
                QTimer.singleShot(300, self.start_mini)

            def start_mini(self):
                try:
                    header = self.maxi_page.layout().itemAt(0).layout()
                    assert header.itemAt(header.count() - 1).widget() is self.mini_button
                    self.mini_button.click()
                    assert self.view_mode.mini and not self.cards
                    QTimer.singleShot(200, self.empty_capture)
                except Exception as error:
                    self.fail(error)

            def empty_capture(self):
                try:
                    assert self.grab().save(str(output / "mini-empty.png"))
                    self.mini_panel.search.setText("рабочий")
                    QTimer.singleShot(200, self.result_capture)
                except Exception as error:
                    self.fail(error)

            def result_capture(self):
                try:
                    assert len(self.cards) == 2
                    for card in self.cards:
                        card.expand.click()
                    QTimer.singleShot(200, self.finish)
                except Exception as error:
                    self.fail(error)

            def finish(self):
                try:
                    for card in self.cards:
                        buttons = card.findChildren(CopyIconButton)
                        assert buttons and all(b.width() == b.height() for b in buttons)
                    totp_card = next(c for c in self.cards if hasattr(c, "totp"))
                    totp_button = next(b for b in totp_card.findChildren(CopyIconButton)
                                       if b.accessibleName() == "Копировать текущий код 2FA")
                    totp_button.click()
                    assert len(self.clipboard.clipboard.text()) == 6
                    assert totp_button.text() == "✓"
                    assert self.grab().save(str(output / "mini-results.png"))
                    cards = list(self.cards)
                    assert QSystemTrayIcon.isSystemTrayAvailable()
                    self.close()
                    assert self.in_tray and not self.isVisible()
                    self.tray.open_action.trigger()
                    assert self.isVisible() and self.view_mode.mini
                    assert self.focusWidget() is self.mini_panel.search
                    assert self.cards == cards and all(c.body.isVisible() for c in cards)
                    self.mini_panel.maxi_action.trigger()
                    assert not self.view_mode.mini
                    assert self.vault_tab.search.text() == "рабочий"
                    self.mini_button.click()
                    self.lock()
                    assert not self.view_mode.mini and not self.cards
                    assert self.settings.data["window_mode"] == "mini"
                except Exception as error:
                    failures.append(type(error).__name__)
                finally:
                    self.exit_application()

            def fail(self, error):
                failures.append(type(error).__name__)
                self.exit_application()

        lifecycle.MainWindow = SmokeWindow
        try:
            runpy.run_path(str(ROOT / "Acc-storage.py"), run_name="__main__")
        except SystemExit as exit_status:
            if exit_status.code:
                failures.append(f"exit={exit_status.code}")
        finally:
            vault.close()
            logging.shutdown()
            lifecycle.ROOT = original_root
            lifecycle.MainWindow = original_window
    report = {"ok": not failures, "errors": failures, "interpreter": sys.executable}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if failures:
        raise RuntimeError("Mini smoke failed: " + ", ".join(failures))
    print("Mini live smoke OK: search, accordions, tray, mode roundtrip, lock")


if __name__ == "__main__":
    main()
