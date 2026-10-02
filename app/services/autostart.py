"""Current-user Windows Startup shortcut; no elevation or global Python."""
import ctypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.settings import ROOT

MARKER = "KeyShelf managed startup"


class AutostartError(ValueError):
    pass


class Guid(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def startup_folder():
    folder = Guid(0xB97D20BB, 0xF46A, 0x4C97, (ctypes.c_ubyte * 8)(0xBA, 0x10, 0x5E, 0x36, 0x08, 0x43, 0x08, 0x54))
    shell = ctypes.WinDLL("shell32")
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(Guid), ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole = ctypes.WinDLL("ole32")
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.c_void_p()
    try:
        if shell.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(pointer)) != 0:
            raise OSError("Startup folder unavailable")
        return Path(ctypes.wstring_at(pointer))
    finally:
        if pointer.value:
            ole.CoTaskMemFree(pointer)


def launch_target():
    if getattr(sys, "frozen", False):
        target = Path(sys.executable).resolve()
        return target, "", target.parent
    return ROOT / ".venv/Scripts/pythonw.exe", f'"{ROOT / "Acc-storage.py"}"', ROOT


def vbs_string(value):
    return '"' + str(value).replace('"', '""') + '"'


def run_vbs(script):
    host = Path(os.environ["SystemRoot"]) / "System32/cscript.exe"
    with tempfile.TemporaryDirectory(prefix="acc-storage-startup-") as folder:
        path = Path(folder) / "shortcut.vbs"
        path.write_text(script, encoding="utf-16")
        return subprocess.run([str(host), "//Nologo", "//U", "//T:10", str(path)], capture_output=True,
                              timeout=10, creationflags=subprocess.CREATE_NO_WINDOW, check=True)


class Autostart:
    def __init__(self, folder=None):
        try:
            self.path = (Path(folder) if folder is not None else startup_folder()) / "KeyShelf.lnk"
        except (OSError, AttributeError):
            self.path = None

    def enabled(self):
        return bool(self.path and self.path.is_file())

    def set_enabled(self, enabled):
        if self.path is None:
            raise AutostartError("Папка автозагрузки Windows недоступна.")
        target, arguments, working_directory = launch_target()
        if enabled and (not target.is_file() or (not getattr(sys, "frozen", False) and not (ROOT / "Acc-storage.py").is_file())):
            raise AutostartError("Не найдена точка входа или проектное окружение приложения.")
        script = f'''Option Explicit
Dim shell, files, link, path
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
path = {vbs_string(self.path)}
Set link = shell.CreateShortcut(path)
If files.FileExists(path) Then
    If link.Description <> {vbs_string(MARKER)} Then WScript.Quit 2
End If
'''
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            script += f'''link.TargetPath = {vbs_string(target)}
link.Arguments = {vbs_string(arguments)}
link.WorkingDirectory = {vbs_string(working_directory)}
link.Description = {vbs_string(MARKER)}
link.IconLocation = {vbs_string(working_directory / "logo.ico")}
link.Save
'''
        else:
            script += 'If files.FileExists(path) Then files.DeleteFile path, True\n'
        try:
            run_vbs(script)
        except (OSError, subprocess.SubprocessError):
            raise AutostartError("Не удалось изменить автозагрузку. Проверьте доступ к папке Startup; посторонний ярлык не перезаписывается.") from None
        if self.enabled() != enabled:
            raise AutostartError("Windows не подтвердила изменение автозагрузки.")
        return enabled
