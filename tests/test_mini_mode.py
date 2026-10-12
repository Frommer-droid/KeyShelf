"""Поиск, компактные карточки, отдельная геометрия и восстановление из трея."""
import json

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QPushButton, QSystemTrayIcon

from app.core.models import Account, Field, Service
from app.core.settings import Settings
from app.services.vault import Vault
from app.ui.main_window import MainWindow
from app.ui.widgets import CopyIconButton
from tests.test_ui import PASSWORD, make_window


def settle(qtapp):
    for _ in range(6):
        qtapp.processEvents()


@pytest.mark.parametrize("kind", ["api", "account", "other", "legacy"])
def test_mini_global_search_accordion_and_copy(qtapp, tmp_path, kind):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.services.append(Service("second", "Второй сервис"))
        window.snapshot.accounts.append(Account(
            service_id="second", service="Второй сервис", title="Нужная метка", kind=kind,
            login="synthetic@example.invalid", fields=[
                Field("API-ключ" if kind == "api" else "Поле 1" if kind == "other"
                      else "Пароль", "synthetic-mini-value")]))
        window.vault_tab.favorites.setChecked(True)
        window.vault_tab.filter_other.setChecked(True)
        window.mini_button.click()
        assert window.view_mode.mini
        assert window.maxi_page.isHidden() and window.mini_panel.isVisible()
        assert not window.cards and window.mini_panel.scroll.isHidden()
        window.mini_panel.search.setText("нужная метка")
        settle(qtapp)
        assert len(window.cards) == 1
        card = window.cards[0]
        assert not card.body.isVisible()
        assert card.expand.text() == "Второй сервис · Нужная метка"
        assert [b.text() for b in card.findChildren(QPushButton) if b.isVisible()] == [
            "Второй сервис · Нужная метка"]
        assert not any(b.text() in ("Изменить", "Удалить", "☆", "★")
                       for b in card.findChildren(QPushButton))
        card.expand.click()
        settle(qtapp)
        assert card.body.isVisible()
        copies = [b for b in card.findChildren(QPushButton)
                  if b.accessibleName().startswith("Копировать")]
        assert all(isinstance(b, CopyIconButton) and b.width() == b.height() for b in copies)
        copies[-1].click()
        assert qtapp.clipboard().text() == "synthetic-mini-value"
        assert copies[-1].text() == "✓"
        window.mini_panel.search.setText("synthetic-mini-value")
        settle(qtapp)
        assert not window.cards
        assert window.mini_panel.scroll.isVisible()
        window.mini_panel.search.clear()
        settle(qtapp)
        assert not window.cards and window.mini_panel.scroll.isHidden()
    finally:
        window.exit_application()


def test_mini_geometry_roundtrip_and_restart(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    settings_path = window.settings.path
    vault_path = window.path
    try:
        area = window.screen().availableGeometry()
        window.resize(min(1180, area.width() - 60), min(810, area.height() - 100))
        window.move(area.x() + 20, area.y() + 20)
        settle(qtapp)
        maxi = QRect(window.geometry())
        window.vault_tab.search.setText("Основной")
        window.mini_button.click()
        settle(qtapp)
        assert window.mini_panel.search.text() == "Основной"
        assert window.width() < maxi.width()
        window.resize(590, 310)
        window.move(180, 190)
        window.save_geometry()
        mini = QRect(window.geometry())
        window.mini_panel.maxi_action.trigger()
        settle(qtapp)
        assert not window.view_mode.mini
        assert window.geometry() == maxi
        assert window.vault_tab.search.text() == "Основной"
        window.mini_button.click()
        settle(qtapp)
        assert window.width() == mini.width()
        assert window.geometry().topLeft() == mini.topLeft()
        before = QRect(window.geometry())
        for _ in range(10):
            window.view_mode.fit()
        assert window.geometry() == before
        window.save_geometry()
        loaded = Settings(settings_path)
        assert loaded.data["window_mode"] == "mini"
        assert loaded.data["window_width"] == maxi.width()
        assert loaded.data["mini_width"] == mini.width()
        assert "Основной" not in settings_path.read_text(encoding="utf-8")
    finally:
        window.exit_application()
    reopened = MainWindow(Settings(settings_path))
    try:
        assert not reopened.view_mode.mini  # Сначала разблокировка.
        reopened.opened(Vault.open(vault_path, PASSWORD))
        reopened.show()
        settle(qtapp)
        assert reopened.view_mode.mini
        assert reopened.mini_panel.search.text() == ""
        assert reopened.width() == mini.width()
        assert not reopened.cards
    finally:
        reopened.exit_application()


@pytest.mark.parametrize("mini", [False, True])
def test_both_modes_close_to_tray_with_query_and_expansion(qtapp, tmp_path, monkeypatch, mini):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    window = make_window(qtapp, tmp_path)
    try:
        window.view_mode.set_mini(mini)
        search = window.mini_panel.search if mini else window.vault_tab.search
        search.setText("Основной")
        settle(qtapp)
        card = window.cards[0]
        card.expand.click()
        vault = window.vault
        window.close()
        assert window.in_tray and not window.isVisible() and window.vault is vault
        window.tray.open_action.trigger()
        settle(qtapp)
        assert window.isVisible() and not window.in_tray
        assert window.view_mode.mini == mini
        assert window.cards[0] is card and card.body.isVisible()
        assert search.text() == "Основной"
        window.lock()
        assert not window.view_mode.mini
        assert window.mini_panel.search.text() == ""
        window.close()
        assert window.in_tray and not window.isVisible()
        window.tray.open_action.trigger()
        assert window.isVisible() and window.vault is None
    finally:
        window.exit_application()


def test_mini_settings_validation_and_defaults(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings(path).data["window_mode"] == "maxi"
    path.write_text(json.dumps({"window_mode": "bad", "mini_width": -5,
                                "mini_height": 999999}), encoding="utf-8")
    loaded = Settings(path).data
    assert loaded["window_mode"] == "maxi"
    assert loaded["mini_width"] == 320 and loaded["mini_height"] == 8000


def test_mini_maximized_restore_and_scale(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.showMaximized()
        settle(qtapp)
        window.mini_button.click()
        settle(qtapp)
        assert not window.isMaximized()
        window.mini_panel.search.setText("Основной")
        window.system_tab.scale_combo.setCurrentIndex(window.system_tab.scale_combo.findData(30))
        settle(qtapp)
        assert window.view_mode.mini
        assert window.minimumWidth() == round(360 * window.ui_scale.state.scale_factor)
        assert window.cards[0].layout().spacing() == round(10 * window.ui_scale.state.scale_factor)
        window.mini_panel.maxi_action.trigger()
        settle(qtapp)
        assert window.isMaximized()
        assert window.minimumWidth() == round(940 * window.ui_scale.state.scale_factor)
    finally:
        window.exit_application()


def test_mini_many_results_scroll_and_disconnected_monitor(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.settings.data.update(mini_pos_x=90000, mini_pos_y=-90000, mini_height=320)
        service = window.current_service()
        window.snapshot.accounts = [Account(service_id=service, title=f"Метка {i}", kind="api",
                                            fields=[Field("API-ключ", "synthetic")])
                                    for i in range(30)]
        window.mini_button.click()
        window.mini_panel.search.setText("Метка")
        settle(qtapp)
        assert len(window.cards) == 30
        assert window.height() <= 320
        assert window.mini_panel.scroll.verticalScrollBar().maximum() > 0
        assert window.screen().availableGeometry().contains(window.geometry())
        window.cards[0].expand.click()
        settle(qtapp)
        assert window.height() <= 320
        window.mini_panel.search.clear()
        settle(qtapp)
        assert window.height() < 150
        assert window.settings.data["mini_height"] == 320
    finally:
        window.exit_application()
