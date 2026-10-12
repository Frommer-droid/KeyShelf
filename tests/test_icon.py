import ctypes
import struct

from PySide6.QtGui import QIcon, QImage

from app.core.resources import APP_USER_MODEL_ID, resource_path
from app.core.settings import ROOT, Settings
from app.ui.main_window import MainWindow

SIZES = {16, 24, 32, 48, 64, 128, 256}


def test_ico_contains_real_png_frames():
    raw = resource_path("logo.ico").read_bytes()
    assert struct.unpack_from("<HHH", raw) == (0, 1, 7)
    found = set()
    for index in range(7):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from("<BBBBHHII", raw, 6 + index * 16)
        width, height = width or 256, height or 256
        assert planes == 1 and bits == 32
        payload = raw[offset:offset + length]
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        frame = QImage.fromData(payload, "PNG")
        assert (frame.width(), frame.height()) == (width, height)
        assert frame.hasAlphaChannel()
        assert frame.pixelColor(0, 0).alpha() == 0
        assert frame.pixelColor(width // 2, height // 2).alpha() >= 240
        found.add(width)
    assert found == SIZES


def test_icon_resources_application_and_window(qtapp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resource_path("logo.ico") == ROOT / "logo.ico"
    icon = QIcon(str(resource_path("logo.ico")))
    assert {s.width() for s in icon.availableSizes()} == SIZES
    assert not qtapp.windowIcon().isNull()
    window = MainWindow(Settings(tmp_path / "settings.json"))
    try:
        assert not window.windowIcon().isNull()
        assert window.windowIcon().cacheKey() == qtapp.windowIcon().cacheKey()
    finally:
        window.exit_application()
    shell = ctypes.WinDLL("shell32")
    shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.POINTER(ctypes.c_wchar_p)]
    shell.GetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    result = ctypes.c_wchar_p()
    assert shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(result)) == 0
    try:
        assert result.value == APP_USER_MODEL_ID
    finally:
        ole = ctypes.WinDLL("ole32")
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree(ctypes.cast(result, ctypes.c_void_p))
