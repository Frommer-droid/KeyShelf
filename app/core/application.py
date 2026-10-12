import ctypes
import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.localization import install_russian
from app.core.resources import APP_USER_MODEL_ID, resource_path
from app.core.settings import ROOT
from app.ui.main_window import MainWindow
from app.ui.style_appendix import appendix
from app.ui.theme import apply_theme


def create_application(argv=None):
    if sys.platform == "win32":
        shell = ctypes.WinDLL("shell32")
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        if shell.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID) != 0:
            raise RuntimeError("Не удалось установить идентификатор приложения Windows.")
    application = QApplication(argv if argv is not None else sys.argv)
    application.setQuitOnLastWindowClosed(False)
    icon = QIcon(str(resource_path("logo.ico")))
    if icon.isNull():
        raise RuntimeError("Не удалось загрузить иконку приложения logo.ico.")
    application.setWindowIcon(icon)
    apply_theme(application)
    application.setStyleSheet(application.styleSheet() + appendix())
    application.setApplicationName("KeyShelf")
    install_russian(application)
    return application


def main():
    # Только маркер запуска. Не включать debug PyKeePass или текст исключений.
    logging.basicConfig(filename=ROOT / "startup.log", filemode="w", level=logging.INFO,
                        format="%(message)s", encoding="utf-8")
    application = create_application()
    window = MainWindow()
    window.show_at_startup()
    logging.info("Приложение запущено; interpreter=%s", sys.executable)
    return application.exec()
