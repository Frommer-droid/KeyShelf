"""Real editor save keeps the edited UUID in the visible viewport."""
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest

from app.core.models import Account, Field, Service, Snapshot
from app.ui.record_dialog import RecordDialog
from app.ui.widgets import Button
from tests.test_ui import make_window, process


@pytest.mark.parametrize("rename", [False, True])
def test_editor_save_keeps_record_anchor(qtapp, tmp_path, rename):
    window = make_window(qtapp, tmp_path)
    try:
        incoming = Snapshot([Service("test", "Test")], [Account(service_id="test", title=f"Account {i:02}",
            login=f"synthetic-{i}", kind="account", fields=[Field("Пароль", "synthetic"), Field("Секрет 2FA", "")])
            for i in range(40)])
        window.saved(window.vault.import_records(incoming)[0])
        window.vault_tab.all_services.click()
        QTest.qWait(100)
        target = window.cards[20]
        record_id = target.account.id
        scroll = window.vault_tab.scroll
        scroll.ensureWidgetVisible(target.expand, 0, 0)
        QTest.qWait(50)
        before = scroll.verticalScrollBar().value()
        assert before > 0
        def save():
            editor = window.findChild(RecordDialog)
            assert editor is not None
            editor.inputs["login"].setText("changed-synthetic-login")
            if rename:
                editor.inputs["title"].setText("Account 35 edited")
            editor.submit()
        QTimer.singleShot(0, save)
        edit = next(button for button in target.findChildren(Button) if button.text() == "Изменить")
        edit.click()
        process(qtapp, lambda: not window.busy)
        QTest.qWait(200)
        edited = next(card for card in window.cards if card.account.id == record_id)
        assert edited.account.login == "changed-synthetic-login"
        assert edited.expand.hasFocus()
        assert scroll.verticalScrollBar().value() > 0
        top = edited.expand.mapTo(scroll.viewport(), edited.expand.rect().topLeft()).y()
        assert 0 <= top < scroll.viewport().height()
        if not rename:
            assert scroll.verticalScrollBar().value() >= before - edited.height()
    finally:
        window.exit_application()
