import json

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.core.models import Account
from app.core.settings import Settings
from app.services.vault import Vault
from app.ui.main_window import MainWindow
from tests.test_ui import PASSWORD, make_window


def selected(window):
    return {kind for kind, button in window.type_filter_buttons() if button.isChecked()}


def test_service_filters_switch_rename_lock_and_restart(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    path = window.path
    settings_path = window.settings.path
    first = window.current_service()
    try:
        window.saved(window.vault.account(Account(service_id=first, title="API", kind="api")))
        window.saved(window.vault.service("Second"))
        second = next(s.id for s in window.snapshot.services if s.name == "Second")
        window.saved(window.vault.account(Account(service_id=second, title="Other", kind="other")))

        def select(service):
            for row in range(window.vault_tab.services.count()):
                window.vault_tab.services.setCurrentRow(row)
                if window.current_service() == service:
                    return
            raise AssertionError("Service missing")

        select(first)
        window.vault_tab.filter_api.click()
        select(second)
        assert selected(window) == set()
        window.vault_tab.filter_other.click()
        assert [card.account.kind for card in window.cards] == ["other"]
        select(first)
        assert selected(window) == {"api"}
        assert [card.account.kind for card in window.cards] == ["api"]
        window.saved(window.vault.service("Renamed", id=first))
        assert selected(window) == {"api"}
        select(second)
        assert selected(window) == {"other"}
        window.vault_tab.filter_other.click()
        select(first)
        select(second)
        assert selected(window) == set()
        select(first)
        window.lock()
        window.opened(Vault.open(path, PASSWORD))
        select(first)
        assert selected(window) == {"api"}
    finally:
        window.exit_application()
    reopened = MainWindow(Settings(settings_path))
    try:
        reopened.opened(Vault.open(path, PASSWORD))
        for row in range(reopened.vault_tab.services.count()):
            reopened.vault_tab.services.setCurrentRow(row)
            if reopened.current_service() == first:
                break
        assert selected(reopened) == {"api"}
    finally:
        reopened.exit_application()


def test_settings_isolate_vaults_and_sanitize_filters(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    first, second = tmp_path / "first.kdbx", tmp_path / "second.kdbx"
    settings.remember_service_filters(first, "same-id", ["api", "other"])
    settings.remember_service_filters(second, "same-id", ["account"])
    loaded = Settings(settings.path)
    assert loaded.service_filters(first, "same-id") == ["api", "other"]
    assert loaded.service_filters(second, "same-id") == ["account"]
    assert Settings(tmp_path / "fresh.json").data["service_type_filters"] == {}
    settings.path.write_text(json.dumps({"service_type_filters": {
        "bad": [], "vault": {"invalid": None, "valid": ["api", "unknown", "api", {}]}}}), encoding="utf-8")
    assert Settings(settings.path).data["service_type_filters"] == {"vault": {"valid": ["api"]}}


def test_service_click_refreshes_once_and_reselect_clears_search(qtapp, tmp_path, monkeypatch):
    window = make_window(qtapp, tmp_path)
    try:
        window.saved(window.vault.service("Second"))
        qtapp.processEvents()
        refreshes = []
        refresh = window.refresh_cards

        def observed_refresh(*args):
            refreshes.append(window.current_service())
            refresh(*args)

        monkeypatch.setattr(window, "refresh_cards", observed_refresh)
        services = window.vault_tab.services
        window.vault_tab.search.setText("Основной")
        refreshes.clear()
        item = services.item(1)
        QTest.mouseClick(services.viewport(), Qt.MouseButton.LeftButton,
                         pos=services.visualItemRect(item).center())
        assert services.currentItem() is item
        assert window.vault_tab.search.text() == ""
        assert len(refreshes) == 1
        window.vault_tab.search.setText("Основной")
        refreshes.clear()
        QTest.mouseClick(services.viewport(), Qt.MouseButton.LeftButton,
                         pos=services.visualItemRect(item).center())
        assert window.vault_tab.search.text() == ""
        assert len(refreshes) == 1
        refreshes.clear()
        QTest.mouseClick(services.viewport(), Qt.MouseButton.LeftButton,
                         pos=services.visualItemRect(item).center())
        assert not refreshes
    finally:
        window.exit_application()
