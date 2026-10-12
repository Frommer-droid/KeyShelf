from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets import Button, label


class SystemTab(QWidget):
    def __init__(self):
        super().__init__()
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(18)
        security = QGroupBox("Открытие хранилища")
        security_layout = QVBoxLayout(security)
        self.master_password = QCheckBox("Использовать мастер-пароль")
        security_layout.addWidget(self.master_password)
        layout.addWidget(security)
        display_group = QGroupBox("Поля записей")
        display_layout = QVBoxLayout(display_group)
        self.hide_record_secrets = QCheckBox("Скрывать пароли и ключи")
        display_layout.addWidget(self.hide_record_secrets)
        layout.addWidget(display_group)
        self.scale_group = QGroupBox("Масштаб интерфейса")
        scale_layout = QVBoxLayout(self.scale_group)
        scale_row = QHBoxLayout()
        scale_label = label("Масштаб:")
        self.scale_combo = QComboBox()
        self.scale_combo.setAccessibleName("Масштаб интерфейса")
        self.scale_combo.setToolTip("Поправка к автоматическому масштабу: 100% — без поправки")
        scale_label.setBuddy(self.scale_combo)
        for delta in range(-50, 51, 10):
            self.scale_combo.addItem(f"{100 + delta}%", delta)
        scale_row.addWidget(scale_label)
        scale_row.addWidget(self.scale_combo)
        scale_row.addStretch()
        scale_layout.addLayout(scale_row)
        layout.addWidget(self.scale_group)
        self.autostart_group = QGroupBox("Автозагрузка")
        startup_row = QHBoxLayout(self.autostart_group)
        self.autostart = QCheckBox("Загружать при загрузке системы")
        self.start_minimized = QCheckBox("Запускать свернутым")
        self.autostart.setToolTip("Запускать приложение после входа в Windows")
        self.start_minimized.setToolTip("Запускать сразу в системном трее; открыть окно можно кликом по иконке")
        startup_row.addWidget(self.autostart)
        startup_row.addWidget(self.start_minimized)
        startup_row.addStretch()
        layout.addWidget(self.autostart_group)
        layout.addWidget(label("Импорт и экспорт", "sectionTitle"))
        layout.addWidget(label("Файл обмена JSON содержит ключи и пароли в открытом виде. Импорт полностью заменяет сервисы и записи открытой базы содержимым файла. Предыдущая версия сохраняется в резервной копии рядом с базой.", "muted", True))
        exchange_row = QHBoxLayout()
        self.import_data = Button("Импортировать JSON…")
        self.export_data = Button("Экспортировать JSON…")
        exchange_row.addWidget(self.import_data)
        exchange_row.addWidget(self.export_data)
        exchange_row.addStretch()
        layout.addLayout(exchange_row)
        layout.addWidget(label("Резервные копии", "sectionTitle"))
        layout.addWidget(label("Перед каждым изменением предыдущая версия сохраняется рядом с файлом как .kdbx.bak. Копия тоже зашифрована. Для восстановления откройте её и сохраните копию под новым именем.", "muted", True))
        row = QHBoxLayout()
        self.backup = Button("Сохранить копию…")
        self.open_backup = Button("Открыть резервную копию…")
        row.addWidget(self.backup)
        row.addWidget(self.open_backup)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(label("История буфера Windows и сторонние менеджеры могут сохранять копии. Приложение просит Windows не включать скопированное в историю; уже созданные копии оно не удаляет.", "muted", True))
        layout.addWidget(label("Мастер-пароль восстановить нельзя. Блокировка очищает интерфейс и ссылки приложения; гарантированное стирание памяти Python не обеспечивается.", "muted", True))
        layout.addStretch()
        self.scroll.setWidget(page)
        shell.addWidget(self.scroll)
