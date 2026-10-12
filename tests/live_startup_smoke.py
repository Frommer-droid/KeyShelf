"""Cold native tray start with isolated preferences and no real Startup writes."""
import runpy
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer

import app.core.application as lifecycle
from app.core.settings import ROOT, Settings
from app.services.autostart import Autostart
from app.ui.main_window import MainWindow


def main():
    failures = []
    with tempfile.TemporaryDirectory(prefix="acc-storage-tray-start-") as folder:
        settings = Settings(Path(folder) / "settings.json")
        settings.data["start_minimized"] = True
        settings.save()

        class SmokeWindow(MainWindow):
            def __init__(self):
                super().__init__(settings, Autostart(Path(folder) / "Startup"))
                QTimer.singleShot(250, self.verify)

            def verify(self):
                try:
                    assert not self.isVisible() and self.in_tray
                    assert self.tray.isVisible() and self.vault is None
                    self.tray.open_action.trigger()
                    assert self.isVisible() and not self.in_tray
                    assert self.vault is None and self.stack.currentIndex() == 0
                except Exception as error:
                    failures.append(type(error).__name__)
                finally:
                    self.tray.exit_action.trigger()

        lifecycle.MainWindow = SmokeWindow
        try:
            runpy.run_path(str(ROOT / "Acc-storage.py"), run_name="__main__")
        except SystemExit as result:
            assert result.code == 0
    assert not failures, failures
    print("Cold tray startup: hidden window, live tray, restore and clean exit OK")


if __name__ == "__main__":
    main()
