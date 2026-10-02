from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from app.core.models import BASE_FIELD_LABELS
from app.services.totp import generator
from app.ui.totp_value import TotpValue
from app.ui.widgets import Button, CopyIconButton, FavoriteButton, SecretValue, label


class AccountCard(QFrame):
    def __init__(self, account, copy, edit, delete, favorite=None, compact=False):
        super().__init__()
        self.account = account
        self.compact = compact
        self.setObjectName("accountCard")
        self.setProperty("recordKind", "account" if account.kind == "legacy" else account.kind)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)
        title = f"{account.service} · {account.title}" if compact and account.service else account.title
        self.header_title = title
        self.expand = Button(title)
        self.expand.setCheckable(True)
        self.expand.setObjectName("cardHeader")
        self.expand.setProperty("recordKind", "account" if account.kind == "legacy" else account.kind)
        self.expand.setAccessibleName(f"Раскрыть запись {title}")
        header = QHBoxLayout()
        header.addWidget(self.expand, 1)
        if account.kind == "api" and not compact:
            badge = label("$" if account.api_paid else "⓪", "apiPaid" if account.api_paid else "apiFree")
            badge.setAccessibleName("Платный API" if account.api_paid else "Бесплатный API")
            badge.setToolTip(badge.accessibleName())
            badge.setFixedWidth(24)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.addWidget(badge)
        if account.kind in ("api", "other") and not compact:
            field_name = "API-ключ" if account.kind == "api" else "Поле 1"
            if account.kind == "other" and account.field_layout:
                field_name = account.field_layout[0]
            key = next((f.value for f in account.fields if f.label == field_name), "")
            self.quick_copy = CopyIconButton(lambda value=key: copy(value),
                                             "Копировать API-ключ" if account.kind == "api" else "Копировать первое поле")
            header.addWidget(self.quick_copy)
        if favorite and not compact:
            self.favorite_button = FavoriteButton(lambda: favorite(account))
            self.favorite_button.setChecked(account.favorite)
            self.favorite_button.setAccessibleName("Убрать из избранного" if account.favorite else "Добавить в избранное")
            self.favorite_button.setToolTip(self.favorite_button.accessibleName())
            header.addWidget(self.favorite_button)
        layout.addLayout(header)
        if account.kind in ("api", "account", "other"):
            if not compact:
                header.addWidget(Button("Изменить", lambda: edit(account)))
                header.addWidget(Button("Удалить", lambda: delete(account), "danger_btn"))
            self.build_compact_body(layout, account, copy)
            return
        summary = " · ".join(x for x in [account.service, account.login, account.project, account.tags] if x)
        if not compact:
            layout.addWidget(label(summary, "muted", True))
        self.body = QWidget()
        self.body.setObjectName("cardBody")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 4, 0, 0)
        body.setSpacing(14)
        self.values = []
        fields = [("Логин", account.login, False)] if account.login else []
        fields += [(f.label, f.value, f.secret) for f in account.fields]
        for caption, value, secret in fields:
            if not value:
                continue
            row = QGridLayout()
            row.setColumnStretch(0, 1)
            row.addWidget(label(caption, "muted"), 0, 0)
            display = SecretValue(value) if secret else label(value, "fieldValue", True)
            row.addWidget(display, 1, 0)
            copy_btn = self.copy_button(lambda v=value: copy(v), f"Копировать поле {caption}")
            row.addWidget(copy_btn, 0, 2, 2, 1, Qt.AlignmentFlag.AlignVCenter)
            if secret:
                show = Button("Показать", display.toggle)
                show.setAccessibleName(f"Показать или скрыть поле {caption}")
                display.button = show
                self.values.append(display)
                row.addWidget(show, 0, 1, 2, 1, Qt.AlignmentFlag.AlignVCenter)
            body.addLayout(row)
        if account.notes:
            body.addWidget(label("Комментарий" if account.kind == "api" else "Заметка", "muted"))
            body.addWidget(label(account.notes, wrap=True))
        if not compact:
            actions = QHBoxLayout()
            actions.addWidget(Button("Изменить", lambda: edit(account)))
            actions.addWidget(Button("Удалить", lambda: delete(account), "danger_btn"))
            actions.addStretch()
            body.addLayout(actions)
        self.body.hide()
        layout.addWidget(self.body)
        self.expand.toggled.connect(self.toggle)

    def build_compact_body(self, layout, account, copy):
        self.body = QWidget()
        self.body.setObjectName("cardBody")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 4, 0, 0)
        body.setSpacing(8)
        self.values = []
        fields = {f.label: f.value for f in account.fields}
        rows = [("API-ключ", fields.get("API-ключ", ""))] if account.kind == "api" else [
            ("Логин", account.login), ("Пароль", fields.get("Пароль", ""))]
        if account.kind == "other":
            rows = [(f"Поле {i}", fields.get(f"Поле {i}", "")) for i in range(1, 4)]
        rows += [(f.label, f.value) for f in account.fields
                 if f.label not in BASE_FIELD_LABELS[account.kind]]
        if account.field_layout is not None:
            visible = dict(rows)
            rows = [(name, visible[name]) for name in account.field_layout if name in visible]
        for caption, value in rows:
            if not value:
                continue
            row = QHBoxLayout()
            display = QLineEdit(value)
            display.setReadOnly(True)
            display.setAccessibleName(caption)
            if account.kind != "other":
                display.setPlaceholderText(caption)
            row.addWidget(display, 1)
            button = self.copy_button(lambda v=value: copy(v), f"Копировать поле {caption}")
            row.addWidget(button)
            body.addLayout(row)
        seed = fields.get("Секрет 2FA", "")
        if account.kind == "account" and seed:
            try:
                generator(seed)
            except ValueError:
                body.addWidget(label("Некорректный секрет 2FA. Исправьте его в редакторе.", "error", True))
            else:
                row = QHBoxLayout()
                self.totp = TotpValue(seed)
                row.addWidget(self.totp, 1)
                button = self.copy_button(lambda: copy(self.totp.code()),
                                          "Копировать текущий код 2FA")
                row.addWidget(button)
                self.values.append(self.totp)
                body.addLayout(row)
        self.body.hide()
        layout.addWidget(self.body)
        self.expand.toggled.connect(self.toggle)

    def copy_button(self, copy, caption):
        if self.compact:
            return CopyIconButton(copy, caption)
        button = Button("Копировать", lambda checked=False: copy())
        button.setAccessibleName(caption)
        return button

    def toggle(self, expanded):
        self.body.setVisible(expanded)
        title = self.header_title
        self.expand.setText(title)
        if self.account.kind in ("api", "account") and hasattr(self, "totp"):
            self.totp.set_expanded(expanded)
        if not expanded:
            self.hide_secrets()

    def hide_secrets(self):
        if self.account and self.account.kind in ("api", "account", "other"):
            self.expand.setChecked(False)
            return
        for value in self.values:
            value.hide_secret()

    def scrub(self):
        for value in self.values:
            value.scrub()
        self.account = None
        self.header_title = ""
        # Удаление сигналов с замыканиями, содержащими значения.
        for button in self.findChildren(Button):
            if isinstance(button, CopyIconButton):
                button.scrub()
            button.blockSignals(True)
            if button.callback:
                button.clicked.disconnect(button.callback)
                button.callback = None
        self.expand.blockSignals(True)
        self.expand.toggled.disconnect(self.toggle)
        for child in self.findChildren(QWidget):
            if hasattr(child, "setText"):
                child.setText("")
