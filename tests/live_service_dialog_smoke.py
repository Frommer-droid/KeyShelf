"""Живая проверка геометрии диалога сервиса на синтетическом хранилище."""
import logging
import runpy
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QInputDialog

import app.core.application as lifecycle
import app.ui.main_window as window_module
import app.ui.ui_scale_runtime as scale_module
from app.core.settings import ROOT, Settings
from app.services.autostart import Autostart
from app.services.ui_scale import UIScaleState
from app.services.vault import Vault


def main():
    failures = []
    observations = []

    class ObservedDialog(QInputDialog):
        def __init__(self, parent):
            super().__init__(parent)
            self.resizes = []

        def resizeEvent(self, event):
            self.resizes.append(QSize(event.size()))
            super().resizeEvent(event)

    with tempfile.TemporaryDirectory(prefix="keyshelf-service-smoke-") as directory:
        folder = Path(directory)
        vault, _ = Vault.create(folder / "synthetic.kdbx", "synthetic-dialog-passphrase-123")
        state = vault.service("Тестовый сервис")

        class SmokeWindow(window_module.MainWindow):
            def __init__(self):
                super().__init__(Settings(folder / "settings.json"), Autostart(folder / "Startup"))
                self.opened((vault, state))
                QTimer.singleShot(200, self.verify)

            def verify(self):
                try:
                    for existing in (False, True):
                        QTimer.singleShot(200, self.start_observation)
                        QTimer.singleShot(1000, self.finish_observation)
                        self.edit_service(existing)
                    assert len(observations) == 2
                    assert not failures, failures
                except Exception as error:
                    failures.append(repr(error))
                finally:
                    self.exit_application()

            def start_observation(self):
                dialog = self.dialogs[-1]
                dialog.resizes.clear()
                dialog.stable_size = QSize(dialog.size())
                dialog.setTextValue("Синтетическое название сервиса")

            def finish_observation(self):
                dialog = self.dialogs[-1]
                try:
                    assert dialog.isVisible()
                    assert not dialog.resizes, dialog.resizes[:10]
                    assert dialog.size() == dialog.stable_size
                    assert dialog.minimumHeight() <= dialog.height() <= dialog.maximumHeight()
                    observations.append(dialog.windowTitle())
                except Exception as error:
                    failures.append(repr(error))
                finally:
                    dialog.reject()

        window_module.QInputDialog = ObservedDialog
        scale_module.resolve_screen = lambda screen, delta: UIScaleState(130, 0, 130)
        lifecycle.MainWindow = SmokeWindow
        lifecycle.ROOT = folder
        try:
            runpy.run_path(str(ROOT / "Acc-storage.py"), run_name="__main__")
        except SystemExit as result:
            assert result.code == 0
        finally:
            vault.close()
            logging.shutdown()
        assert not failures, failures
        assert "interpreter=" in (folder / "startup.log").read_text(encoding="utf-8")
    print("Native source startup: new/edit service dialogs at 130%, stable geometry, typing and cancel OK")


if __name__ == "__main__":
    main()
