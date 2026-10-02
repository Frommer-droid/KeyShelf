import secrets

from PySide6.QtCore import QMimeData, QObject

OWNER = "application/x-secret-vault-owner"


class Clipboard(QObject):
    def __init__(self, clipboard, parent=None):
        super().__init__(parent)
        self.clipboard = clipboard
        self.value = None
        self.token = None

    def copy(self, value):
        self.value = value
        self.token = secrets.token_hex(16).encode()
        mime = QMimeData()
        mime.setText(value)
        mime.setData(OWNER, self.token)
        # Windows clipboard policy: не включать в историю и cloud sync.
        mime.setData('application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"', b"\x00\x00\x00\x00")
        mime.setData('application/x-qt-windows-mime;value="CanUploadToCloudClipboard"', b"\x00\x00\x00\x00")
        self.clipboard.setMimeData(mime)

    def clear_owned(self):
        mime = self.clipboard.mimeData()
        if self.token and mime and bytes(mime.data(OWNER)) == self.token and mime.text() == self.value:
            self.clipboard.clear()
        self.value = self.token = None
