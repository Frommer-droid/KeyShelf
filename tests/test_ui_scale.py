import json

import pytest
from PySide6.QtCore import QSize

from app.core.models import Account, Field
from app.core.settings import Settings
from app.services.ui_scale import UIScaleState, calculate_scale, normalize_delta, target_window_size
from app.ui.cards import AccountCard
from app.ui.main_window import MainWindow
from app.ui.record_dialog import RecordDialog
from tests.test_ui import make_window


@pytest.mark.parametrize("width,height,dpi,delta,expected", [
    (2560, 1440, 96, 0, (100, 100)),
    (1920, 1080, 96, 0, (80, 80)),
    (1280, 720, 96, 0, (70, 70)),
    (2560, 1440, 192, 50, (200, 300)),
    (1280, 720, 96, -50, (70, 35)),
    (2560, 1440, 96, -50, (100, 50)),
])
def test_screen_scale(width, height, dpi, delta, expected):
    state = calculate_scale(width, height, dpi, delta)
    assert (state.auto_percent, state.final_percent) == expected
    assert state.scale_factor == state.final_percent / 100


def test_scale_settings_migration_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ui_scale_percent": 130}), encoding="utf-8")
    settings = Settings(path)
    assert settings.data["ui_scale_delta_percent"] == 30
    settings.save()
    assert Settings(path).data["ui_scale_delta_percent"] == 30
    path.write_text(json.dumps({"ui_scale_delta_percent": "bad", "ui_scale_mode": "manual"}), encoding="utf-8")
    assert Settings(path).data["ui_scale_mode"] == "auto"
    assert Settings(path).data["ui_scale_delta_percent"] == 0
    assert normalize_delta(999) == 50 and normalize_delta(-999) == -50
    assert normalize_delta(True) == 0
    assert calculate_scale(0, 0, float("nan")).final_percent == 100
    assert target_window_size(1000, 800, 2, 500, 400, 1920, 1080) == (1920, 1080)


def test_scale_whole_ui_roundtrip_dialog_and_no_screen_resize(qtapp, tmp_path, monkeypatch):
    window = MainWindow(Settings(tmp_path / "settings.json"))
    try:
        combo = window.system_tab.scale_combo
        assert not hasattr(window.system_tab, "scale_info")
        assert combo.count() == 11
        assert [combo.itemData(i) for i in range(11)] == list(range(-50, 51, 10))
        initial = window.ui_scale.state
        layout = window.centralWidget().layout()
        base = layout.property("uiScaleBaseline")
        before_spacing = layout.spacing()
        before_qss = qtapp.styleSheet()
        combo.setCurrentIndex(combo.findData(30))
        larger = window.ui_scale.state
        assert larger.scale_factor > initial.scale_factor
        assert layout.spacing() > before_spacing
        assert qtapp.styleSheet() != before_qss
        assert Settings(window.settings.path).data["ui_scale_delta_percent"] == 30
        dialog = RecordDialog(window, [], kind="api")
        dialog.show()
        qtapp.processEvents()
        assert dialog.comment.minimumHeight() == round(90 * larger.scale_factor)
        assert dialog.comment.maximumHeight() == 16777215
        assert dialog.minimumWidth() == round(500 * larger.scale_factor)
        assert dialog.property("uiScaleInitialSizeApplied")
        dialog.add_field.click()
        qtapp.processEvents()
        assert len(dialog.extra_inputs) == 1
        assert dialog.add_field.minimumWidth() == dialog.add_field.sizeHint().height()
        card = AccountCard(Account(title="Synthetic", kind="api", fields=[Field("API-ключ", "synthetic")]),
                           lambda value: True, lambda account: None, lambda account: None)
        window.vault_tab.cards_layout.insertWidget(0, card)
        qtapp.processEvents()
        assert card.layout().spacing() == round(10 * larger.scale_factor)
        assert card.quick_copy.minimumWidth() == card.quick_copy.sizeHint().height()
        window.resize(1800, 1300)
        size = QSize(window.size())
        with monkeypatch.context() as patch:
            patch.setattr("app.ui.ui_scale_runtime.resolve_screen", lambda screen, delta: UIScaleState(110, 30, 145))
            window.ui_scale.apply("screen-metrics")
            assert window.ui_scale.state.final_percent == 145
            assert window.size() == size
        combo.setCurrentIndex(combo.findData(0))
        assert window.ui_scale.state == initial
        assert layout.spacing() == before_spacing
        assert layout.contentsMargins().left() == round(base["margins"][0] * initial.scale_factor)
        assert dialog.comment.minimumHeight() == round(90 * initial.scale_factor)
        assert card.quick_copy.minimumWidth() == card.quick_copy.sizeHint().height()
        window.ui_scale.apply("runtime")
        assert layout.spacing() == before_spacing
        dialog.reject()
        dialog.deleteLater()
    finally:
        window.exit_application()


def test_maximized_window_not_resized_and_new_window_remembers(qtapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    window = MainWindow(Settings(settings_path))
    try:
        window.showMaximized()
        qtapp.processEvents()
        size = QSize(window.size())
        window.system_tab.scale_combo.setCurrentIndex(window.system_tab.scale_combo.findData(-20))
        assert window.isMaximized() and window.size() == size
    finally:
        window.exit_application()
    reopened = MainWindow(Settings(settings_path))
    try:
        assert reopened.system_tab.scale_combo.currentData() == -20
        assert reopened.ui_scale.state.delta_percent == -20
    finally:
        reopened.exit_application()


@pytest.mark.parametrize("kind", ["api", "account", "other", "legacy"])
def test_cards_have_final_scale_on_first_show(qtapp, tmp_path, monkeypatch, kind):
    first_spacing = []

    class ObservedCard(AccountCard):
        def showEvent(self, event):
            first_spacing.append(self.layout().spacing())
            super().showEvent(event)

    monkeypatch.setattr("app.ui.main_window.AccountCard", ObservedCard)
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.accounts[0].kind = kind
        window.system_tab.scale_combo.setCurrentIndex(
            window.system_tab.scale_combo.findData(-30))
        qtapp.processEvents()
        expected = round(10 * window.ui_scale.state.scale_factor)
        assert expected != 10
        first_spacing.clear()
        for _ in range(10):
            window.refresh_cards()
            qtapp.processEvents()
            qtapp.processEvents()
        assert first_spacing == [expected] * 10
    finally:
        window.exit_application()
