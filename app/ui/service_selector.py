from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import Button, label


class ServiceComboBox(QComboBox):
    def showPopup(self):
        self.open_search()


class ServiceSelector(QWidget):
    """Keep the selected UUID separate from the search text and record draft."""

    def __init__(self, services, service_id, parent=None):
        super().__init__(parent)
        self.combo = ServiceComboBox()
        self.combo.open_search = self.choose_service
        self.combo.setAccessibleName("Сервис")
        for service in sorted(services, key=lambda item: item.name.casefold().replace("ё", "е")):
            self.combo.addItem(service.name, service.id)
        self.combo.setCurrentIndex(max(0, self.combo.findData(service_id)))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.combo, 1)

    def choose_service(self):
        editor = self.window()
        picker = QDialog(editor)
        picker.setWindowTitle("Сервис")
        picker.setMinimumSize(420, 360)
        layout = QVBoxLayout(picker)
        search = QLineEdit()
        search.setAccessibleName("Поиск названия сервиса")
        search.setPlaceholderText("Найти сервис…")
        layout.addWidget(search)
        results = QListWidget()
        results.setAccessibleName("Результаты поиска сервисов")
        layout.addWidget(results)
        empty = label("Сервисы не найдены", "muted")
        layout.addWidget(empty)
        actions = QHBoxLayout()
        actions.addStretch()
        select = Button("Выбрать", picker.accept, "success_btn")
        actions.addWidget(select)
        actions.addWidget(Button("Отмена", picker.reject))
        layout.addLayout(actions)

        def update():
            results.clear()
            terms = search.text().casefold().split()
            for index in range(self.combo.count()):
                name = self.combo.itemText(index)
                if all(term in name.casefold() for term in terms):
                    results.addItem(name)
                    item = results.item(results.count() - 1)
                    item.setData(Qt.ItemDataRole.UserRole, self.combo.itemData(index))
                    if item.data(Qt.ItemDataRole.UserRole) == self.combo.currentData():
                        results.setCurrentItem(item)
            if results.currentItem() is None and results.count():
                results.setCurrentRow(0)
            empty.setVisible(results.count() == 0)
            select.setEnabled(results.currentItem() is not None)

        search.textChanged.connect(update)
        results.itemDoubleClicked.connect(lambda item: picker.accept())
        # Locking the vault rejects the editor and its nested search dialog.
        editor.finished.connect(picker.reject)
        update()
        search.setFocus()
        try:
            if picker.exec() == QDialog.DialogCode.Accepted and results.currentItem():
                service_id = results.currentItem().data(Qt.ItemDataRole.UserRole)
                self.combo.setCurrentIndex(self.combo.findData(service_id))
        finally:
            editor.finished.disconnect(picker.reject)
            picker.setParent(None)
            picker.deleteLater()
