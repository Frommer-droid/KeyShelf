"""Снимок только нашего HWND с native рамкой через Windows PrintWindow."""
import ctypes
from ctypes import wintypes

from PySide6.QtGui import QImage


def capture_window(hwnd, path):
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]

    class BitmapHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                    ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                    ("image_size", wintypes.DWORD), ("xppm", wintypes.LONG), ("yppm", wintypes.LONG),
                    ("used", wintypes.DWORD), ("important", wintypes.DWORD)]

    gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.POINTER(BitmapHeader), wintypes.UINT]
    rect = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    width, height = rect.right - rect.left, rect.bottom - rect.top
    source_dc = user.GetDC(hwnd)
    dc = gdi.CreateCompatibleDC(source_dc)
    bitmap = gdi.CreateCompatibleBitmap(source_dc, width, height)
    old = gdi.SelectObject(dc, bitmap)
    try:
        if not user.PrintWindow(hwnd, dc, 2):
            return False
        gdi.SelectObject(dc, old)
        header = BitmapHeader()
        header.size = ctypes.sizeof(header)
        header.width, header.height = width, -height
        header.planes, header.bits = 1, 32
        raw = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(dc, bitmap, 0, height, raw, ctypes.byref(header), 0) != height:
            return False
        image = QImage(raw.raw, width, height, width * 4, QImage.Format.Format_RGB32).copy()
        return image.save(str(path), "PNG")
    finally:
        gdi.SelectObject(dc, old)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)
        user.ReleaseDC(hwnd, source_dc)
