import copy

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget

from app.core.models import Account, Field, Service
from app.services.vault import Vault
from app.ui.dialogs import AccountDialog
from app.ui.record_dialog import RecordDialog
from app.ui.widgets import Button
from tests.test_ui import PASSWORD, make_window


def make_editor(parent, services, account=None, service_id=None, kind="account"):
    if kind == "legacy":
        return AccountDialog(parent, services, account, service_id)
    return RecordDialog(parent, services, account, service_id, kind)


@pytest.mark.parametrize("kind", ["account", "api", "other", "legacy"])
def test_editor_service_move_updates_counts_and_reopens(qtapp, tmp_path, kind):
    window = make_window(qtapp, tmp_path)
    editor = None
    try:
        source = window.current_service()
        window.saved(window.vault.service("Destination"))
        target = next(s.id for s in window.snapshot.services if s.name == "Destination")
        fields = {"account": [Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "")],
                  "api": [Field("API-ключ", "synthetic-key")],
                  "other": [Field(f"Поле {i}", f"value-{i}") for i in range(1, 4)],
                  "legacy": [Field("Custom", "synthetic-secret")]}
        window.saved(window.vault.account(Account(service_id=source, title="Move me", kind=kind,
                                                login="login" if kind in ("account", "legacy") else "",
                                                fields=fields[kind], alias="alias", notes="notes",
                                                favorite=True, api_paid=kind == "api")))
        account = next(a for a in window.snapshot.accounts if a.title == "Move me")
        original = copy.deepcopy(account)
        editor = make_editor(window, window.snapshot.services, account, target, kind)
        assert editor.service.currentData() == source
        editor.service.setCurrentIndex(editor.service.findData(target))
        assert account == original
        editor.submit()
        assert editor.result_account.service_id == target
        window.saved(window.vault.account(editor.result_account))
        items = window.vault_tab.services
        captions = {items.item(i).data(Qt.ItemDataRole.UserRole): items.item(i).text()
                    for i in range(items.count())}
        assert captions[source].startswith("1  ·")
        assert captions[target].startswith("1  ·")
        assert all(card.account.id != account.id for card in window.cards)
        items.setCurrentRow(next(i for i in range(items.count())
                                 if items.item(i).data(Qt.ItemDataRole.UserRole) == target))
        assert [card.account.id for card in window.cards] == [account.id]
        path = window.path
        window.lock()
        reopened_vault, reopened = Vault.open(path, PASSWORD)
        reopened_vault.close()
        moved = next(a for a in reopened.accounts if a.id == account.id)
        assert moved.service_id == target
        assert moved.title == original.title
        assert moved.alias == original.alias
        assert moved.login == original.login
        assert moved.notes == original.notes
        assert moved.fields == original.fields
        assert moved.favorite == original.favorite
        assert moved.api_paid == original.api_paid
    finally:
        if editor:
            editor.scrub()
            editor.close()
        window.exit_application()


def test_service_search_filters_by_words_selects_uuid_and_cancel_keeps_draft(qtapp):
    services = [Service("one", "Одинаковый"), Service("two", "Одинаковый"),
                Service("nested", "Работа / Почта"), Service("root", "Без сервиса")]
    account = Account(service_id="two", title="Synthetic", kind="account")
    editor = RecordDialog(None, services, account)
    editor.show()
    failures = []

    def choose():
        try:
            picker = editor.findChild(QDialog)
            search = picker.findChild(QLineEdit)
            results = picker.findChild(QListWidget)
            assert results.currentItem().data(Qt.ItemDataRole.UserRole) == "two"
            search.setText("нет совпадений")
            assert results.count() == 0
            button = next(b for b in picker.findChildren(Button) if b.text() == "Выбрать")
            assert not button.isEnabled()
            search.setText("  ПОЧТА работа  ")
            assert results.count() == 1
            assert results.currentItem().data(Qt.ItemDataRole.UserRole) == "nested"
            button.click()
        except BaseException as error:
            failures.append(error)
            editor.findChild(QDialog).reject()

    try:
        QTimer.singleShot(0, choose)
        editor.service.showPopup()
        assert not failures, failures
        assert editor.service.currentData() == "nested"
        assert account.service_id == "two"
        assert editor.account.service_id == "two"
        QTimer.singleShot(0, lambda: editor.findChild(QDialog).reject())
        editor.service.showPopup()
        assert editor.service.currentData() == "nested"
        editor.reject()
        assert editor.result_account is None
        assert account.service_id == "two"
    finally:
        editor.scrub()
        editor.close()


@pytest.mark.parametrize("kind", ["account", "api", "other", "legacy"])
def test_new_editor_defaults_to_selected_service(qtapp, kind):
    editor = make_editor(None, [Service("one", "First"), Service("two", "Second")],
                         service_id="two", kind=kind)
    try:
        assert editor.service.currentData() == "two"
        editor.inputs["title"].setText("Synthetic")
        editor.submit()
        assert editor.result_account.service_id == "two"
    finally:
        editor.scrub()
        editor.close()
