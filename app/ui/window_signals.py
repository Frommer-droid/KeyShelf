from PySide6.QtGui import QKeySequence, QShortcut


def connect_signals(window):
    tab = window.vault_tab
    tab.services.currentItemChanged.connect(window.select_service)
    tab.services.itemClicked.connect(window.click_service)
    tab.splitter.splitterMoved.connect(lambda *_: window.geometry_timer.start(400))
    tab.search.textChanged.connect(window.refresh_cards)
    window.mini_panel.search.textChanged.connect(window.refresh_cards)
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
