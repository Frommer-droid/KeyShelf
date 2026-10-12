import copy

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QScroller,
    QVBoxLayout,
    QWidget,
)

from app.core.models import Account, Field
from app.ui.service_selector import ServiceSelector
from app.ui.widgets import Button, FavoriteButton, label


class PasswordDialog(QDialog):
    def __init__(self, parent, create=False):
        super().__init__(parent)
        self.setWindowTitle("Создать хранилище" if create else "Разблокировать")
        self.setMinimumWidth(440)
        self.create = create
        layout = QVBoxLayout(self)
        layout.addWidget(label("Мастер-пароль", "sectionTitle"))
        layout.addWidget(label("Сохраните пароль в надёжном месте: восстановить его нельзя." if create else "Введите мастер-пароль выбранного файла.", "muted", True))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName("Мастер-пароль")
        layout.addWidget(self.password)
        self.repeat = QLineEdit()
        self.repeat.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat.setAccessibleName("Повтор мастер-пароля")
        if create:
            layout.addWidget(label("Повторите пароль"))
            layout.addWidget(self.repeat)
        self.error = label("", "error", True)
        layout.addWidget(self.error)
        row = QHBoxLayout()
        row.addWidget(Button("Создать" if create else "Открыть", self.submit, "success_btn"))
        row.addWidget(Button("Отмена", self.reject))
        layout.addLayout(row)
        self.password.returnPressed.connect(self.submit)
        self.repeat.returnPressed.connect(self.submit)

    def submit(self):
        if self.create and len(self.password.text()) < 12:
            self.error.setText("Используйте не менее 12 символов, лучше длинную парольную фразу.")
        elif self.create and self.password.text() != self.repeat.text():
            self.error.setText("Пароли не совпадают.")
        elif not self.password.text():
            self.error.setText("Введите мастер-пароль.")
        else:
            self.accept()

    def scrub(self):
        self.password.clear()
        self.repeat.clear()


class FieldEditor(QWidget):
    def __init__(self, field, remove, hide_record_secrets=True):
        super().__init__()
        self.hide_record_secrets = hide_record_secrets
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.caption = QLineEdit(field.label)
        self.caption.setPlaceholderText("Название поля")
        self.caption.setAccessibleName("Название поля")
        self.value = QLineEdit(field.value)
        self.value.setAccessibleName("Значение поля")
        self.secret = QCheckBox("Секрет")
        self.secret.setChecked(field.secret)
        self.mode()
        self.secret.toggled.connect(self.mode)
        row.addWidget(self.caption, 2)
        row.addWidget(self.value, 3)
        row.addWidget(self.secret)
        delete = Button("−", lambda: remove(self), "addFieldButton")
        delete.setAccessibleName("Удалить поле")
        delete.setToolTip("Удалить поле")
        delete.setProperty("uiSquareButton", True)
        delete.setFixedWidth(delete.sizeHint().height())
        row.addWidget(delete)

    def mode(self):
        self.value.setEchoMode(QLineEdit.EchoMode.Password if self.hide_record_secrets and self.secret.isChecked() else QLineEdit.EchoMode.Normal)

    def field(self):
        return Field(self.caption.text().strip(), self.value.text(), self.secret.isChecked())

    def scrub(self):
        self.caption.clear()
        self.value.clear()


class AccountDialog(QDialog):
    def __init__(self, parent, services, account=None, service_id=None):
        super().__init__(parent)
        self.hide_record_secrets = (parent.settings.data["hide_record_secrets"]
                                    if parent is not None and hasattr(parent, "settings") else True)
        self.setWindowTitle("Изменить аккаунт" if account else "Новый аккаунт")
        self.setMinimumSize(780, 570)
        self.account = copy.deepcopy(account) if account else Account(service_id=service_id or "")
        self.result_account = None
        layout = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        QScroller.grabGesture(area.viewport(), QScroller.ScrollerGestureType.TouchGesture)
        page = QWidget()
        content = QVBoxLayout(page)
        content.setSpacing(8)
        self.form = form = QFormLayout()
        form.setVerticalSpacing(8)
        self.service_selector = ServiceSelector(services, self.account.service_id)
        self.service = self.service_selector.combo
        form.addRow(self.service_selector)
        self.record_type = QComboBox()
        self.record_type.setAccessibleName("Тип записи")
        self.record_type.addItem("Сохранённые поля", "legacy")
        form.addRow(self.record_type)
        self.inputs = {}
        for key, caption in [("title", "Название"), ("alias", "Метка"), ("login", "Логин"),
                             ("project", "Проект"), ("tags", "Метки"), ("notes", "Заметка")]:
            edit = QLineEdit(getattr(self.account, key))
            edit.setAccessibleName(caption)
            edit.installEventFilter(self)
            form.addRow(caption, edit)
            self.inputs[key] = edit
        self.favorite = FavoriteButton()
        self.favorite.setAccessibleName("Избранное записи")
        self.favorite.setToolTip("Избранное записи")
        self.favorite.setChecked(self.account.favorite)
        content.addLayout(form)
        content.addWidget(label("Поля аккаунта", "sectionTitle"))
        content.addWidget(label("Пароль, основной API-ключ, тестовый ключ — каждое поле с отдельным названием.", "muted", True))
        self.field_layout = QVBoxLayout()
        self.field_layout.setSpacing(8)
        self.rows = []
        self.active_field = None
        self.insert_at_start = False
        content.addLayout(self.field_layout)
        for f in self.account.fields or [Field("Пароль", "")]:
            self.add_field(f)
        self.field_actions = QWidget()
        actions = QHBoxLayout(self.field_actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.add_field_button = Button("+ Поле", self.add_empty_field)
        self.add_field_button.setAccessibleName("Добавить пустое поле")
        actions.addWidget(self.add_field_button, 1)
        actions.addWidget(self.favorite, 1)
        content.addWidget(self.field_actions)
        content.addStretch()
        area.setWidget(page)
        layout.addWidget(area)
        self.error = label("", "error", True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(Button("Сохранить", self.submit, "success_btn"))
        buttons.addWidget(Button("Отмена", self.reject))
        layout.addLayout(buttons)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn and hasattr(self, "rows"):
            self.active_field = next((row for row in self.rows if watched in (row.caption, row.value)), None)
            self.insert_at_start = watched in self.inputs.values() and watched is not self.inputs["notes"]
        return super().eventFilter(watched, event)

    def add_empty_field(self):
        number = 1
        labels = {row.caption.text() for row in self.rows}
        while f"Дополнительное поле {number}" in labels:
            number += 1
        self.add_field(Field(f"Дополнительное поле {number}", ""), focus=True)

    def add_field(self, field, focus=False):
        row = FieldEditor(field, self.remove_field, self.hide_record_secrets)
        index = len(self.rows)
        if focus:
            if self.active_field in self.rows:
                index = self.rows.index(self.active_field) + 1
            elif self.insert_at_start:
                index = 0
        self.rows.insert(index, row)
        self.field_layout.insertWidget(index, row)
        row.caption.installEventFilter(self)
        row.value.installEventFilter(self)
        if focus:
            row.value.setFocus()

    def remove_field(self, row):
        row.scrub()
        self.rows.remove(row)
        self.field_layout.removeWidget(row)
        row.deleteLater()

    def submit(self):
        if not self.inputs["title"].text().strip():
            self.error.setText("Укажите название аккаунта.")
            self.inputs["title"].setFocus()
            return
        if not self.service.currentData():
            self.error.setText("Выберите сервис.")
            return
        if any(not r.caption.text().strip() for r in self.rows):
            self.error.setText("Подпишите каждое поле или уберите пустое.")
            return
        a = self.account
        a.service_id = self.service.currentData()
        for key, edit in self.inputs.items():
            setattr(a, key, edit.text())
        a.favorite = self.favorite.isChecked()
        a.fields = [r.field() for r in self.rows]
        self.result_account = copy.deepcopy(a)
        self.accept()

    def scrub(self):
        for edit in self.inputs.values():
            edit.clear()
        for row in self.rows:
            row.scrub()
        self.account = self.result_account = None
