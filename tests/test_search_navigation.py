"""Реальные события клавиатуры для поиска и аккордеонов в обоих режимах."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.core.models import Account, Field, Service
from tests.test_mini_mode import settle
from tests.test_ui import make_window


def test_service_search_is_independent_and_survives_refresh(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        selected = window.current_service()
        window.snapshot.services += [Service("empty", "Пустой сервис"), Service("nested", "Почта / Работа")]
        window.refresh_services()
        tab = window.vault_tab
        tab.search.setText("Тестовый проект")
        tab.service_search.setText("РАБОТА почта")
        def visible():
            return [tab.services.item(i).toolTip() for i in range(tab.services.count())
                    if not tab.services.item(i).isHidden()]
        assert visible() == ["Почта / Работа"]
        assert window.current_service() == selected
        assert tab.search.text() == "Тестовый проект"
        assert len(window.cards) == 1  # Global record search ignores the service-list filter.
        window.refresh_services()
        assert visible() == ["Почта / Работа"]
        tab.service_search.setText("несуществующий")
        assert not visible() and not tab.service_empty.isHidden()
        tab.service_search.setText("ПУСТОЙ")
        assert visible() == ["Пустой сервис"]  # Services without entries are searchable.
        tab.service_search.clear()
        assert len(visible()) == len(window.snapshot.services)
        assert tab.service_empty.isHidden()
        tab.service_search.setText("почта")
        window.lock()
        assert not tab.service_search.text()
    finally:
        window.exit_application()


@pytest.mark.parametrize("mini", [False, True])
@pytest.mark.parametrize("query", ["О", " ", "несуществующая запись"])
def test_escape_clears_nonempty_search(qtapp, tmp_path, mini, query):
    window = make_window(qtapp, tmp_path)
    try:
        window.view_mode.set_mini(mini)
        search = window.mini_panel.search if mini else window.vault_tab.search
        search.setText(query)
        search.setFocus()
        settle(qtapp)
        QTest.keyClick(search, Qt.Key.Key_Escape)
        settle(qtapp)
        assert search.text() == ""
        assert search.hasFocus()
        assert window.isVisible()
        if mini:
            assert not window.cards and window.mini_panel.scroll.isHidden()
    finally:
        window.exit_application()


@pytest.mark.parametrize("mini", [False, True])
@pytest.mark.parametrize("enter", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_tab_focuses_first_result_then_enter_toggles(qtapp, tmp_path, mini, enter):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.accounts = [
            Account(service_id=window.current_service(), title=title, kind="api",
                    fields=[Field("API-ключ", "synthetic-navigation-value")])
            for title in ("Запись Б", "Запись А")
        ]
        window.view_mode.set_mini(mini)
        search = window.mini_panel.search if mini else window.vault_tab.search
        search.setText("Запись")
        search.setFocus()
        settle(qtapp)
        assert len(window.cards) == 2
        first, second = window.cards
        QTest.keyClick(search, Qt.Key.Key_Tab)
        settle(qtapp)
        assert first.expand.hasFocus()
        assert not first.body.isVisible() and not second.body.isVisible()
        QTest.keyClick(first.expand, enter)
        settle(qtapp)
        assert first.body.isVisible() and not second.body.isVisible()
        QTest.keyClick(first.expand, enter)
        settle(qtapp)
        assert not first.body.isVisible()
        # С пустым поиском сохраняется глобальное скрытие секретов по Esc.
        search.clear()
        if not mini:
            window.cards[0].expand.click()
            search.setFocus()
            QTest.keyClick(search, Qt.Key.Key_Escape)
            assert not window.cards[0].expand.isChecked()
    finally:
        window.exit_application()


@pytest.mark.parametrize("mini", [False, True])
def test_tab_without_results_keeps_normal_focus_navigation(qtapp, tmp_path, mini):
    window = make_window(qtapp, tmp_path)
    try:
        window.view_mode.set_mini(mini)
        search = window.mini_panel.search if mini else window.vault_tab.search
        search.setText("несуществующая запись")
        search.setFocus()
        settle(qtapp)
        assert not window.cards
        QTest.keyClick(search, Qt.Key.Key_Tab)
        settle(qtapp)
        assert search.text() == "несуществующая запись"
        assert not window.cards
    finally:
        window.exit_application()


def test_all_services_stays_first_and_sorts_every_record(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.services.append(Service("second", "Second"))
        window.snapshot.accounts.extend([
            Account(service_id="second", title="alpha", kind="api", fields=[Field("API-ключ", "key")]),
            Account(service_id="second", title="Zulu", favorite=True, kind="api", fields=[Field("API-ключ", "key")]),
        ])
        window.refresh_services()
        tab = window.vault_tab
        assert tab.all_services.text() == "Все сервисы"
        tab.all_services.click()
        assert len(window.cards) == 3
        assert [c.account.title for c in window.cards] == ["alpha", "Zulu", "Основной аккаунт"]
        tab.service_search.setText("no matches")
        assert tab.all_services.isVisible()
        window.refresh_services()
        assert tab.all_services.isChecked()
        assert tab.services.currentRow() == -1
        assert len(window.cards) == 3
        assert window.tabs.tabText(1) == "Настройки"
    finally:
        window.exit_application()


def test_all_services_button_stays_fixed_while_services_scroll(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        tab = window.vault_tab
        window.snapshot.services.extend(Service(str(i), f"Service {i:03}") for i in range(100))
        window.refresh_services()
        settle(qtapp)
        position = tab.all_services.mapTo(window, tab.all_services.rect().topLeft())
        scrollbar = tab.services.verticalScrollBar()
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        settle(qtapp)
        assert tab.all_services.isVisible()
        assert tab.all_services.mapTo(window, tab.all_services.rect().topLeft()) == position
        tab.all_services.click()
        assert tab.all_services.isChecked() and window.current_service() is None
        tab.services.setCurrentRow(tab.services.count() - 1)
        assert not tab.all_services.isChecked() and window.current_service() is not None
        window.lock()
        assert not tab.all_services.isEnabled()
    finally:
        window.exit_application()
