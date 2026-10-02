"""Проверяет настоящий launcher, окно и уход в трей; завершает свой процесс."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

from app.core.settings import ROOT


def main():
    api = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    api.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    api.IsWindowVisible.argtypes = [wintypes.HWND]
    api.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    api.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    api.SendMessageW.restype = ctypes.c_ssize_t
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    cmd_mode = "--cmd" in sys.argv
    found = []
    descendants = set()

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]

    def collect_children():
        handle = kernel.CreateToolhelp32Snapshot(2, 0)
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        pairs = []
        try:
            ok = kernel.Process32FirstW(handle, ctypes.byref(entry))
            while ok:
                pairs.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
                ok = kernel.Process32NextW(handle, ctypes.byref(entry))
            for _ in range(3):
                for pid, parent, _executable in pairs:
                    if parent in descendants:
                        descendants.add(pid)
        finally:
            kernel.CloseHandle(handle)
        return {pid for pid, _, _ in pairs}

    command = ["cmd.exe", "/c", str(ROOT / "Запустить.cmd")] if cmd_mode else [str(pythonw), str(ROOT / "Acc-storage.py")]
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    descendants.add(process.pid)

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in descendants and api.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(256)
            api.GetWindowTextW(hwnd, text, 256)
            if text.value == "KeyShelf":
                found.append(hwnd)
        return True

    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not found:
            assert process.poll() in (None, 0) if cmd_mode else process.poll() is None, "Launcher exited before creating window"
            collect_children()
            api.EnumWindows(visit, 0)
            time.sleep(0.05)
        assert found, "Visible window not found"
        time.sleep(0.3)
        assert process.poll() in (None, 0) if cmd_mode else process.poll() is None
        assert api.SendMessageW(found[0], 0x007F, 0, 0), "Native small window icon missing"
        assert api.SendMessageW(found[0], 0x007F, 1, 0), "Native large window icon missing"
        api.PostMessageW(found[0], 0x0010, 0, 0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and api.IsWindowVisible(found[0]):
            time.sleep(0.05)
        assert not api.IsWindowVisible(found[0]), "Close must hide the locked window in tray"
        pid = wintypes.DWORD()
        api.GetWindowThreadProcessId(found[0], ctypes.byref(pid))
        assert pid.value in descendants, "Only the launched fixture may be terminated"
        handle = kernel.OpenProcess(1, False, pid.value)
        assert handle, "Cannot terminate launcher fixture"
        try:
            assert kernel.TerminateProcess(handle, 0), "Cannot stop launcher fixture"
        finally:
            kernel.CloseHandle(handle)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0
        assert not stdout
        assert not stderr
        log = (ROOT / "startup.log").read_text(encoding="utf-8")
        assert str(pythonw) in log
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    print(f"Actual {'Запустить.cmd' if cmd_mode else 'pythonw'} launcher: visible window, native small/large icons, startup marker, close to tray, empty stdout/stderr: OK; fixture explicitly terminated by verifier; verifier={sys.executable}")


if __name__ == "__main__":
    main()
