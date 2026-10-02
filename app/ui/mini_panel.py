"""Компактная панель поиска и чтения записей."""
from PySide6.QtWidgets import QLineEdit, QScrollArea, QStyle, QVBoxLayout, QWidget


class MiniPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: сервис, логин, метка…")
        self.search.setAccessibleName("Поиск по всему хранилищу")
        self.search.setClearButtonEnabled(True)
        self.maxi_action = self.search.addAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton),
            QLineEdit.ActionPosition.TrailingPosition)
        self.maxi_action.setText("Макси")
        self.maxi_action.setToolTip("Макси — полный режим")
        layout.addWidget(self.search)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_page = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_page)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_page)
        layout.addWidget(self.scroll, 1)
        self.scroll.hide()
