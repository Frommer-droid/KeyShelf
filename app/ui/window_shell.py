from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.mini_panel import MiniPanel
from app.ui.tabs.system_tab import SystemTab
from app.ui.tabs.vault_tab import VaultTab
from app.ui.widgets import Button, label


def build_shell(window):
    central = QWidget()
    window.maxi_page = central
    layout = QVBoxLayout(central)
    layout.setContentsMargins(22, 18, 22, 12)
    layout.setSpacing(16)
    header = QHBoxLayout()
    header.addWidget(label("KeyShelf", "title"), 1)
    window.open_button = Button("Открыть…", window.open_vault)
    window.create_button = Button("Создать…", lambda: window.open_vault(create=True))
    window.lock_button = Button("Заблокировать", window.lock)
    window.mini_button = Button("Мини", lambda: window.view_mode.set_mini(True))
    window.mini_button.setToolTip("Мини — компактный поиск")
    for button in [window.open_button, window.create_button, window.lock_button]:
        header.addWidget(button)
    header.addWidget(window.mini_button)
    layout.addLayout(header)
    window.tabs = QTabWidget()
    window.stack = QStackedWidget()
    locked = QWidget()
    locked_layout = QVBoxLayout(locked)
    locked_layout.setContentsMargins(50, 50, 50, 50)
    locked_layout.addStretch()
    window.lock_heading = label("Ваши секреты под замком", "title")
    locked_layout.addWidget(window.lock_heading)
    locked_layout.addWidget(label("Создайте хранилище или откройте свой файл KDBX4.\nСервисы и аккаунты появятся после ввода мастер-пароля.", "muted", True))
    actions = QHBoxLayout()
    window.unlock_button = Button("Открыть хранилище", window.unlock, "primaryButton")
    actions.addWidget(window.unlock_button)
    actions.addStretch()
    locked_layout.addLayout(actions)
    locked_layout.addWidget(label("Недавние хранилища", "sectionTitle"))
    window.recent_vaults = QListWidget()
    window.recent_vaults.setAccessibleName("Недавние хранилища")
    window.recent_vaults.setMaximumHeight(280)
    locked_layout.addWidget(window.recent_vaults)
    locked_layout.addStretch()
    window.stack.addWidget(locked)
    window.vault_tab = VaultTab()
    window.stack.addWidget(window.vault_tab)
    window.tabs.addTab(window.stack, "Хранилище")
    window.system_tab = SystemTab()
    window.tabs.addTab(window.system_tab, "Система")
    layout.addWidget(window.tabs, 1)
    window.status = label("Локальное зашифрованное хранилище · KDBX4", "muted", True)
    layout.addWidget(window.status)
    root = QWidget()
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(16)
    root_layout.addWidget(central)
    window.mini_panel = MiniPanel()
    window.mini_panel.hide()
    root_layout.addWidget(window.mini_panel)
    window.setCentralWidget(root)
