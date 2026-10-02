import copy

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import BASE_FIELD_LABELS, EXTRA_FIELD_PREFIX, Account, Field
from app.services.totp import generator
from app.ui.widgets import Button, label


class RecordDialog(QDialog):
    def __init__(self, parent, services, account=None, service_id=None, kind="account"):
        super().__init__(parent)
        self.account = copy.deepcopy(account) if account else Account(service_id=service_id or "", kind=kind)
        self.result_account = None
        self.setWindowTitle("Изменить запись" if account else "Добавить запись")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        content = QWidget()
        self.form = form = QFormLayout(content)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setVerticalSpacing(8)
        self.record_type = QComboBox()
        self.record_type.setAccessibleName("Тип записи")
        for caption, value in [("Аккаунт", "account"), ("API", "api"), ("Другое", "other")]:
            self.record_type.addItem(caption, value)
        self.record_type.setCurrentIndex(self.record_type.findData(self.account.kind))
        type_row = QWidget()
        type_layout = QHBoxLayout(type_row)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.addWidget(self.record_type, 1)
        self.paid = Button("⓪", role="apiPriceToggle")
        self.paid.setCheckable(True)
        self.paid.setChecked(self.account.api_paid)
        self.paid.setProperty("uiSquareButton", True)
        self.paid.setFixedWidth(self.paid.sizeHint().height())
        self.paid.toggled.connect(self.update_price_button)
        self.update_price_button()
        type_layout.addWidget(self.paid)
        form.addRow(type_row)
        if not self.account.service_id and services:
            self.account.service_id = services[0].id
        fields = {f.label: f.value for f in self.account.fields}
        specs = [("title", "Метка", self.account.title if account else ""),
                 ("key", "API-ключ", fields.get("API-ключ", "")),
                 ("login", "Логин", self.account.login),
                 ("password", "Пароль", fields.get("Пароль", "")),
                 ("totp", "Секрет 2FA", fields.get("Секрет 2FA", ""))]
        specs += [(f"other{i}", "", fields.get(f"Поле {i}", "")) for i in range(1, 4)]
        self.all_inputs = {}
        self.field_rows = {}
        for key, caption, value in specs:
            edit = QLineEdit(value)
            edit.setAccessibleName(caption or f"Поле {key[-1]}")
            edit.setPlaceholderText(caption)
            edit.installEventFilter(self)
            field_row = self.make_field_row(edit)
            form.addRow(field_row)
            self.all_inputs[key] = edit
            self.field_rows[key] = field_row
        self.all_inputs["totp"].setPlaceholderText("Необязательно: постоянный секрет Base32")
        self.comment = QTextEdit(self.account.notes)
        self.comment.setAccessibleName("Комментарий")
        self.comment.setPlaceholderText("Комментарий")
        self.comment.installEventFilter(self)
        self.comment.setMinimumHeight(90)
        self.comment.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        form.addRow(self.comment)
        self.active_input = None
        self.orders = {
            "api": [self.all_inputs["key"]],
            "account": [self.all_inputs[key] for key in ("login", "password", "totp")],
            "other": [self.all_inputs[f"other{i}"] for i in range(1, 4)],
        }
        self.extra_inputs = []
        self.extra_rows = []
        self.add_field = Button("+", self.add_empty_field, "addFieldButton")
        self.add_field.setAccessibleName("Добавить пустое поле")
        self.add_field.setToolTip("Добавить пустое поле")
        self.add_field.setProperty("uiSquareButton", True)
        self.add_field.setFixedWidth(self.add_field.sizeHint().height())
        for field in self.account.fields:
            if field.label not in BASE_FIELD_LABELS[self.account.kind]:
                self.add_empty_field(value=field.value, focus=False)
        if self.account.field_layout is not None:
            by_label = {edit.accessibleName(): edit for edit in self.orders[self.account.kind]}
            self.orders[self.account.kind] = [by_label[name] for name in self.account.field_layout if name in by_label]
        self.remove_field = Button("−", self.remove_active_field, "addFieldButton")
        self.remove_field.setAccessibleName("Удалить активное поле вместе с текстом")
        self.remove_field.setToolTip(self.remove_field.accessibleName())
        self.remove_field.setProperty("uiSquareButton", True)
        self.remove_field.setFixedWidth(self.remove_field.sizeHint().height())
        self.remove_field.setEnabled(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.resize(560, 480)
        self.error = label("", "error", True)
        self.error.hide()
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addWidget(self.add_field)
        row.addWidget(self.remove_field)
        row.addStretch()
        row.addWidget(Button("Сохранить", self.submit, "success_btn"))
        row.addWidget(Button("Отмена", self.reject))
        layout.addLayout(row)
        self.current_kind = self.account.kind
        self.record_type.currentIndexChanged.connect(self.select_type)
        self.select_type()

    @staticmethod
    def make_field_row(edit):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        return row

    def update_price_button(self, *args):
        paid = self.paid.isChecked()
        self.paid.setText("$" if paid else "⓪")
        caption = "Платный API" if paid else "Бесплатный API"
        self.paid.setAccessibleName(caption)
        self.paid.setToolTip(f"{caption}. Нажмите, чтобы переключить")

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and hasattr(self, "orders"):
            order = self.orders[self.record_type.currentData()]
            self.active_input = watched if watched in order else None
            if hasattr(self, "remove_field"):
                self.remove_field.setEnabled(self.active_input is not None)
        return super().eventFilter(watched, event)

    def add_empty_field(self, checked=False, *, value="", focus=True):
        edit = QLineEdit(value)
        edit.setAccessibleName(f"{EXTRA_FIELD_PREFIX}{len(self.extra_inputs) + 1}")
        edit.installEventFilter(self)
        row = self.make_field_row(edit)
        self.form.insertRow(self.form.getWidgetPosition(self.comment)[0], row)
        self.extra_inputs.append(edit)
        self.extra_rows.append(row)
        self.renumber_extra_fields()
        current = self.orders[self.record_type.currentData()]
        index = current.index(self.active_input) + 1 if self.active_input in current else len(current)
        for order in self.orders.values():
            order.append(edit)
        current.remove(edit)
        current.insert(index, edit)
        if hasattr(self, "error"):
            self.select_type()
        if focus:
            edit.setFocus()

    def remove_active_field(self):
        order = self.orders[self.record_type.currentData()]
        edit = self.active_input
        if edit not in order:
            return
        index = order.index(edit)
        edit.clear()
        order.remove(edit)
        if edit in self.extra_inputs:
            for other in self.orders.values():
                if edit in other:
                    other.remove(edit)
            i = self.extra_inputs.index(edit)
            row = self.extra_rows.pop(i)
            self.extra_inputs.pop(i)
            self.renumber_extra_fields()
            self.form.takeRow(row)
            row.hide()
            row.deleteLater()
        self.active_input = None
        self.select_type()
        if order:
            order[min(index, len(order) - 1)].setFocus()

    def renumber_extra_fields(self):
        for index, edit in enumerate(self.extra_inputs, 1):
            edit.setAccessibleName(f"{EXTRA_FIELD_PREFIX}{index}")

    def select_type(self, *args):
        kind = self.record_type.currentData()
        if kind != self.current_kind:
            values = [edit.text() for edit in self.orders[self.current_kind]]
            self.current_kind = kind
            self.active_input = None
            for edit in self.all_inputs.values():
                if edit is not self.all_inputs["title"]:
                    edit.clear()
            for edit, row in zip(self.extra_inputs, self.extra_rows, strict=True):
                for order in self.orders.values():
                    if edit in order:
                        order.remove(edit)
                if self.form.getWidgetPosition(row)[0] >= 0:
                    self.form.takeRow(row)
                edit.clear()
                row.hide()
                row.deleteLater()
            self.extra_inputs.clear()
            self.extra_rows.clear()
            base_keys = {"api": ["key"], "account": ["login", "password", "totp"],
                         "other": ["other1", "other2", "other3"]}[kind]
            self.orders[kind] = [self.all_inputs[key] for key in base_keys]
            for edit, value in zip(self.orders[kind], values, strict=False):
                edit.setText(value)
            for value in values[len(base_keys):]:
                self.add_empty_field(value=value, focus=False)
        keys = {"api": ["title", "key"], "account": ["title", "login", "password", "totp"],
                "other": ["title", "other1", "other2", "other3"]}[kind]
        self.inputs = {key: self.all_inputs[key] for key in keys}
        rows = {edit: self.field_rows[key] for key, edit in self.all_inputs.items() if key != "title"}
        rows.update(zip(self.extra_inputs, self.extra_rows, strict=True))
        for row in rows.values():
            if self.form.getWidgetPosition(row)[0] >= 0:
                self.form.takeRow(row)
            row.hide()
        for edit in self.orders[kind]:
            self.form.insertRow(self.form.getWidgetPosition(self.comment)[0], rows[edit])
            rows[edit].show()
        self.paid.setVisible(kind == "api")
        if self.active_input not in self.orders[kind]:
            self.active_input = None
        self.remove_field.setEnabled(self.active_input is not None)
        self.error.clear()
        self.error.hide()

    def submit(self):
        self.error.show()
        a = self.account
        kind = self.record_type.currentData()
        api = kind == "api"
        required = "title"
        if not self.inputs[required].text().strip():
            self.error.setText("Укажите метку.")
            return
        if kind == "account" and self.inputs["totp"].text().strip():
            try:
                generator(self.inputs["totp"].text())
            except ValueError as error:
                self.error.setText(str(error))
                return
        a.title = self.inputs["title"].text().strip()
        a.notes = self.comment.toPlainText()
        a.kind = kind
        a.login = ""
        a.api_paid = False
        if api:
            a.api_paid = self.paid.isChecked()
            a.fields = [Field("API-ключ", self.inputs["key"].text())]
        elif kind == "account":
            a.login = self.inputs["login"].text().strip()
            a.fields = [Field("Пароль", self.inputs["password"].text()),
                        Field("Секрет 2FA", self.inputs["totp"].text().strip())]
        else:
            a.fields = [Field(f"Поле {i}", self.inputs[f"other{i}"].text()) for i in range(1, 4)]
        a.fields.extend(Field(f"{EXTRA_FIELD_PREFIX}{i}", edit.text())
                        for i, edit in enumerate(self.extra_inputs, 1))
        names = {edit: edit.accessibleName() for edit in self.all_inputs.values()}
        names.update({edit: f"{EXTRA_FIELD_PREFIX}{i}" for i, edit in enumerate(self.extra_inputs, 1)})
        a.field_layout = [names[edit] for edit in self.orders[kind]]
        visible = set(a.field_layout)
        for field in a.fields:
            if field.label not in visible:
                field.value = ""
        if "Логин" not in visible:
            a.login = ""
        self.result_account = copy.deepcopy(a)
        self.accept()

    def scrub(self):
        for edit in self.all_inputs.values():
            edit.clear()
        for edit in self.extra_inputs:
            edit.clear()
        if hasattr(self, "comment"):
            self.comment.clear()
        self.account = self.result_account = None
