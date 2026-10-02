import sys

import pytest
from PySide6.QtWidgets import QMessageBox, QSystemTrayIcon

from app.core.settings import Settings
from app.services.autostart import (
    Autostart,
    AutostartError,
    launch_target,
    run_vbs,
    startup_folder,
    vbs_string,
)
from app.ui.main_window import MainWindow
from tests.test_ui import process


def test_native_shortcut_enable_disable_and_foreign_collision(tmp_path):
    assert startup_folder().is_dir()
    manager = Autostart(tmp_path / "Startup с пробелами")
    assert not manager.enabled()
    manager.set_enabled(True)
    target, arguments, working_directory = launch_target()
    inspection = tmp_path / "shortcut-properties.txt"
    run_vbs(f'''Dim link, output
Set link = CreateObject("WScript.Shell").CreateShortcut({vbs_string(manager.path)})
Set output = CreateObject("Scripting.FileSystemObject").CreateTextFile({vbs_string(inspection)}, True, True)
output.WriteLine link.TargetPath
output.WriteLine link.Arguments
output.WriteLine link.WorkingDirectory
output.Close
''')
    lines = inspection.read_text(encoding="utf-16").strip().splitlines()
    assert lines == [str(target), arguments, str(working_directory)]
    assert target.name == "pythonw.exe" and ".venv" in target.parts
    manager.set_enabled(False)
    assert not manager.enabled()
    manager.set_enabled(False)
    run_vbs(f'''Dim link
Set link = CreateObject("WScript.Shell").CreateShortcut({vbs_string(manager.path)})
link.TargetPath = {vbs_string(target)}
link.Description = "Unrelated shortcut"
link.Save
''')
    original = manager.path.read_bytes()
    for enabled in (True, False):
        with pytest.raises(AutostartError):
            manager.set_enabled(enabled)
        assert manager.path.read_bytes() == original


def test_frozen_target(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Application.exe"))
    target, arguments, cwd = launch_target()
    assert target == tmp_path / "Application.exe" and arguments == "" and cwd == tmp_path


def test_startup_controls_persist_failure_rollback_and_restore(qtapp, tmp_path, monkeypatch):
    manager = Autostart(tmp_path / "Startup")
    settings = Settings(tmp_path / "settings.json")
    window = MainWindow(settings, manager)
    try:
        window.show()
        window.tabs.setCurrentIndex(1)
        tab = window.system_tab
        assert not tab.autostart.isChecked() and not tab.start_minimized.isChecked()
        tab.autostart.click()
        process(qtapp, lambda: not window.busy)
        assert manager.enabled() and Settings(settings.path).data["autostart_enabled"]
        tab.start_minimized.click()
        assert Settings(settings.path).data["start_minimized"]
        window.show_at_startup()
        assert window.in_tray and not window.isVisible() and window.vault is None
        window.tray.activate(QSystemTrayIcon.ActivationReason.Trigger)
        assert window.isVisible() and not window.in_tray and window.vault is None
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: None)
        original = manager.set_enabled
        monkeypatch.setattr(manager, "set_enabled", lambda enabled: (_ for _ in ()).throw(AutostartError("Ошибка автозагрузки")))
        tab.autostart.click()
        process(qtapp, lambda: not window.busy)
        assert tab.autostart.isChecked() and manager.enabled()
        monkeypatch.setattr(manager, "set_enabled", original)
        tab.autostart.click()
        process(qtapp, lambda: not window.busy)
        assert not manager.enabled() and not Settings(settings.path).data["autostart_enabled"]
        monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda *args: False)
        window.hide()
        window.show_at_startup()
        assert window.isVisible()
    finally:
        window.exit_application()
