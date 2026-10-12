from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(window.windowIcon(), window)
        self.window = window
        self.setToolTip("KeyShelf")
        self.menu = QMenu(window)
        self.open_action = self.menu.addAction("Открыть")
        self.open_action.triggered.connect(self.restore)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Выход")
        self.exit_action.triggered.connect(window.exit_application)
        self.setContextMenu(self.menu)
        self.activated.connect(self.activate)
        self.show()

    def activate(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def restore(self):
        window = self.window
        if window.exiting:
            return
        window.in_tray = False
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.show()
        window.raise_()
        window.activateWindow()
        if window.view_mode.mini:
            window.mini_panel.search.setFocus()
            window.mini_panel.search.selectAll()
