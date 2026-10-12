from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut


class SearchNavigation(QObject):
    """Клавиатурная навигация из поиска в обоих представлениях."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        for search in (window.vault_tab.search, window.mini_panel.search):
            search.installEventFilter(self)

    def eventFilter(self, search, event):
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if event.key() == Qt.Key.Key_Escape and search.text():
                # Перехватываем Esc до глобальной горячей клавиши скрытия секретов.
                event.accept()
                if event.type() == QEvent.Type.KeyPress:
                    search.clear()
                return True
            if (event.type() == QEvent.Type.KeyPress
                    and event.key() == Qt.Key.Key_Tab
                    and event.modifiers() == Qt.KeyboardModifier.NoModifier
                    and self.window.cards):
                panel = self.window.mini_panel if self.window.view_mode.mini else self.window.vault_tab
                header = self.window.cards[0].expand
                header.setFocus(Qt.FocusReason.TabFocusReason)
                panel.scroll.ensureWidgetVisible(header)
                return True
        return super().eventFilter(search, event)


def connect_signals(window):
    tab = window.vault_tab
    tab.all_services.clicked.connect(window.select_all_services)
    tab.services.currentItemChanged.connect(window.select_service)
    tab.services.itemClicked.connect(window.click_service)
    tab.splitter.splitterMoved.connect(lambda *_: window.geometry_timer.start(400))
    tab.search.textChanged.connect(window.refresh_cards)
    tab.service_search.textChanged.connect(window.filter_services)
    window.mini_panel.search.textChanged.connect(window.refresh_cards)
    window.search_navigation = SearchNavigation(window)
    tab.favorites.toggled.connect(window.refresh_cards)
    tab.filter_api.toggled.connect(window.change_type_filters)
    tab.filter_account.toggled.connect(window.change_type_filters)
    tab.filter_other.toggled.connect(window.change_type_filters)
    tab.add_service.clicked.connect(lambda: window.edit_service())
    tab.edit_service.clicked.connect(lambda: window.edit_service(existing=True))
    tab.delete_service.clicked.connect(window.delete_service)
    tab.add_record.clicked.connect(lambda: window.edit_account())
    window.recent_vaults.itemClicked.connect(window.open_recent)
    window.recent_vaults.itemActivated.connect(window.open_recent)
    window.system_tab.backup.clicked.connect(window.export_backup)
    window.system_tab.master_password.toggled.connect(window.change_master_password)
    window.system_tab.hide_record_secrets.toggled.connect(window.change_record_secret_visibility)
    window.system_tab.autostart.toggled.connect(window.change_autostart)
    window.system_tab.start_minimized.toggled.connect(window.change_start_minimized)
    window.system_tab.import_data.clicked.connect(window.import_data)
    window.system_tab.export_data.clicked.connect(window.export_data)
    window.system_tab.open_backup.clicked.connect(lambda: window.open_vault(backup=True))
    window.shortcuts = []
    for key, callback in [("Ctrl+F", window.focus_search), ("Ctrl+N", window.edit_account),
                          ("Ctrl+L", window.lock), ("Escape", window.hide_secrets)]:
        shortcut = QShortcut(QKeySequence(key), window)
        shortcut.activated.connect(callback)
        window.shortcuts.append(shortcut)
