from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QLabel, QPushButton

from app.ui.theme import enforce_button_proportions


class Button(QPushButton):
    def __init__(self, text, callback=None, role="", parent=None):
        super().__init__(text, parent)
        self.setObjectName(role)
        self.setAccessibleName(text)
        self.callback = callback
        if callback:
            self.clicked.connect(callback)
        enforce_button_proportions([self])

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            enforce_button_proportions([self])


class FavoriteButton(Button):
    def __init__(self, callback=None, parent=None):
        self.hovered = False
        super().__init__("☆", callback, "typeFilter", parent)
        self.setProperty("recordKind", "favorite")
        self.setCheckable(True)
        self.toggled.connect(self.update_star)

    def update_star(self, *args):
        self.setText("★" if self.isChecked() or (self.hovered and self.isEnabled()) else "☆")

    def enterEvent(self, event):
        self.hovered = True
        self.update_star()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered = False
        self.update_star()
        super().leaveEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.update_star()


class CopyIconButton(Button):
    def __init__(self, copy, caption):
        def clicked(checked=False):
            if copy() is not False:
                self.setText("✓")
                self.setAccessibleName("Скопировано")
                self.reset_timer.start(1200)

        super().__init__("⧉", clicked)
        self.caption = caption
        self.setAccessibleName(caption)
        self.setToolTip(caption)
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.reset_icon)
        self.ensurePolished()
        self.setProperty("uiSquareButton", True)
        self.setFixedWidth(self.sizeHint().height())

    def reset_icon(self):
        self.setText("⧉")
        self.setAccessibleName(self.caption)

    def scrub(self):
        self.reset_timer.stop()


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class SecretValue(QLabel):
    def __init__(self, value):
        super().__init__("••••••••••••")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.value = value
        self.revealed = False
        self.setWordWrap(True)
        self.button = None
        self.setAccessibleName("Секрет скрыт")

    def toggle(self):
        if self.revealed:
            self.hide_secret()
        else:
            self.setText(self.value)
            self.setAccessibleName("Секрет показан")
            if self.button:
                self.button.setText("Скрыть")
            self.revealed = True

    def hide_secret(self):
        self.revealed = False
        self.setText("••••••••••••")
        self.setAccessibleName("Секрет скрыт")
        if self.button:
            self.button.setText("Показать")

    def scrub(self):
        self.hide_secret()
        self.value = ""
