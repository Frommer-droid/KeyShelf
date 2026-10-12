"""Deletion follows visible order without opening a neighbour's fields."""
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from app.core.models import Account, Field, Service, Snapshot
from app.ui.widgets import Button
from tests.test_mini_mode import settle
from tests.test_ui import make_window, process


@pytest.mark.parametrize("count,index", [(30, 15), (30, 29), (1, 0)])
def test_delete_selects_visible_successor_and_keeps_position(qtapp, tmp_path, monkeypatch, count, index):
    window = make_window(qtapp, tmp_path)
    try:
        incoming = Snapshot([Service("test", "Test")], [
            Account(service_id="test", title=f"Neighbour {i:02}", kind="other", fields=[
                Field("Поле 1", "synthetic"), Field("Поле 2", ""), Field("Поле 3", "")])
            for i in range(count)] + [Account(service_id="test", title="Hidden", kind="other", fields=[
                Field("Поле 1", "synthetic"), Field("Поле 2", ""), Field("Поле 3", "")])])
        window.saved(window.vault.import_records(incoming)[0])
        window.vault_tab.all_services.click()
        window.vault_tab.search.setText("Neighbour")
        settle(qtapp)
        target = window.cards[index]
        scroll = window.vault_tab.scroll
        scroll.ensureWidgetVisible(target.expand, 0, 0)
        settle(qtapp)
        before = scroll.verticalScrollBar().value()
        monkeypatch.setattr(window, "confirm", lambda *args: True)
        window.delete_account(target.account)
        process(qtapp, lambda: not window.busy)
        settle(qtapp)
        assert len(window.cards) == count - 1
        assert window.vault_tab.search.text() == "Neighbour"
        if window.cards:
            expected = f"Neighbour {index + 1 if index < count - 1 else index - 1:02}"
            focused = next(c for c in window.cards if c.expand.hasFocus())
            assert focused.account.title == expected
            assert not focused.expand.isChecked()
            assert scroll.verticalScrollBar().value() >= min(before, scroll.verticalScrollBar().maximum()) - focused.height()
        else:
            assert not window.cards
    finally:
        window.exit_application()


def test_delete_cancel_preserves_record_and_focus(qtapp, tmp_path, monkeypatch):
    window = make_window(qtapp, tmp_path)
    try:
        card = window.cards[0]
        card.expand.setFocus()
        before = window.path.read_bytes()
        monkeypatch.setattr(window, "confirm", lambda *args: False)
        window.delete_account(card.account)
        assert window.path.read_bytes() == before
        assert window.cards == [card] and card.expand.hasFocus()
    finally:
        window.exit_application()


@pytest.mark.parametrize("index,expanded", [(20, False), (20, True), (39, False)])
def test_real_account_delete_dialog_preserves_late_scroll(qtapp, tmp_path, index, expanded):
    window = make_window(qtapp, tmp_path)
    try:
        incoming = Snapshot([Service("test", "Test")], [Account(service_id="test",
            title=f"Account {i:02}", login=f"synthetic-{i}", kind="account",
            fields=[Field("Пароль", "synthetic"), Field("Секрет 2FA", "")]) for i in range(40)])
        window.saved(window.vault.import_records(incoming)[0])
        window.vault_tab.all_services.click()
        QTest.qWait(100)
        target = window.cards[index]
        if expanded:
            target.expand.click()
            QTest.qWait(50)
        scroll = window.vault_tab.scroll
        scroll.ensureWidgetVisible(target.expand, 0, 0)
        QTest.qWait(50)
        before = scroll.verticalScrollBar().value()
        assert before > 0
        def confirm():
            dialog = window.findChild(QMessageBox)
            assert dialog is not None
            dialog.button(QMessageBox.StandardButton.Yes).click()
        QTimer.singleShot(0, confirm)
        delete = next(button for button in target.findChildren(Button)
                      if button.text() == "Удалить")
        delete.click()
        process(qtapp, lambda: not window.busy)
        QTest.qWait(200)
        focused = next(card for card in window.cards if card.expand.hasFocus())
        assert focused.account.title == f"Account {index + 1 if index < 39 else 38:02}"
        assert scroll.verticalScrollBar().value() >= before - focused.height()
        assert scroll.verticalScrollBar().value() > 0
    finally:
        window.exit_application()
