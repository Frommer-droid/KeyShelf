import copy

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import Account, Field
from app.ui.widgets import Button, label


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
    def __init__(self, field, remove):
        super().__init__()
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
        delete = Button("Убрать", lambda: remove(self))
        row.addWidget(delete)

    def mode(self):
        self.value.setEchoMode(QLineEdit.EchoMode.Password if self.secret.isChecked() else QLineEdit.EchoMode.Normal)

    def field(self):
        return Field(self.caption.text().strip(), self.value.text(), self.secret.isChecked())

    def scrub(self):
        self.caption.clear()
        self.value.clear()


class AccountDialog(QDialog):
    def __init__(self, parent, services, account=None, service_id=None):
        super().__init__(parent)
        self.setWindowTitle("Изменить аккаунт" if account else "Новый аккаунт")
        self.setMinimumSize(780, 570)
        self.account = copy.deepcopy(account) if account else Account(service_id=service_id or "")
        self.result_account = None
        layout = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        page = QWidget()
        content = QVBoxLayout(page)
        form = QFormLayout()
        self.service = QComboBox()
        for s in services:
            self.service.addItem(s.name, s.id)
        index = self.service.findData(self.account.service_id)
        self.service.setCurrentIndex(max(0, index))
        form.addRow("Сервис", self.service)
        self.inputs = {}
        for key, caption in [("title", "Название аккаунта"), ("login", "Логин"),
                             ("project", "Проект"), ("tags", "Метки"), ("notes", "Заметка")]:
            edit = QLineEdit(getattr(self.account, key))
            edit.setAccessibleName(caption)
            form.addRow(caption, edit)
            self.inputs[key] = edit
        self.favorite = QCheckBox("Избранный аккаунт")
        self.favorite.setChecked(self.account.favorite)
        form.addRow(self.favorite)
        content.addLayout(form)
        content.addWidget(label("Поля аккаунта", "sectionTitle"))
        content.addWidget(label("Пароль, основной API-ключ, тестовый ключ — каждое поле с отдельным названием.", "muted", True))
        self.field_layout = QVBoxLayout()
        self.rows = []
        content.addLayout(self.field_layout)
        for f in self.account.fields or [Field("Пароль", "")]:
            self.add_field(f)
        content.addWidget(Button("+ Добавить поле", lambda: self.add_field(Field("", ""))))
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

    def add_field(self, field):
        row = FieldEditor(field, self.remove_field)
        self.rows.append(row)
        self.field_layout.addWidget(row)

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
