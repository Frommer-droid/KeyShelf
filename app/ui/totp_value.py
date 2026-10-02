from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit

from app.services.totp import current_code


class TotpValue(QLineEdit):
    def __init__(self, secret):
        super().__init__()
        self.setReadOnly(True)
        self.setAccessibleName("Текущий код 2FA")
        self.secret = secret
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)

    def code(self):
        return current_code(self.secret)[0]

    def refresh(self):
        code, remaining = current_code(self.secret)
        self.setText(code)
        self.setToolTip(f"2FA: ещё {remaining} с")

    def set_expanded(self, expanded):
        if expanded:
            self.refresh()
            self.refresh_timer.start(250)
        else:
            self.refresh_timer.stop()
            self.clear()

    def scrub(self):
        self.set_expanded(False)
        self.setToolTip("")
        self.secret = ""
