import copy

import pytest
from PySide6.QtWidgets import QLineEdit

from app.core.models import Service, Snapshot
from app.services.exchange import ExchangeError, document, parse
from app.services.vault import Vault
from app.ui.cards import AccountCard
from app.ui.record_dialog import RecordDialog
from app.ui.widgets import Button


def test_comment_absorbs_free_space_after_field_removal(qtapp):
    dialog = RecordDialog(None, [Service("s", "Test")], kind="other")
    try:
        dialog.resize(640, 600)
        dialog.show()
        qtapp.processEvents()
        size = dialog.size()
        title_y = dialog.all_inputs["title"].parentWidget().y()
        comment_height = dialog.comment.height()
        field = dialog.all_inputs["other3"]
        field.setFocus()
        qtapp.processEvents()
        dialog.remove_field.click()
        qtapp.processEvents()
        assert dialog.size() == size
        assert dialog.all_inputs["title"].parentWidget().y() == title_y
        assert dialog.comment.height() > comment_height
        old_height = dialog.comment.height()
        dialog.resize(640, 700)
        qtapp.processEvents()
        assert dialog.all_inputs["title"].parentWidget().y() == title_y
        assert dialog.comment.height() > old_height
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("kind", ["api", "account", "other"])
def test_footer_inserts_below_cursor_and_deletes_contents(qtapp, kind):
    dialog = RecordDialog(None, [Service("s", "Test")], kind=kind)
    try:
        dialog.show()
        qtapp.processEvents()
        first = dialog.orders[kind][0]
        first.setFocus()
        qtapp.processEvents()
        assert dialog.add_field.parentWidget() is dialog
        assert dialog.remove_field.parentWidget() is dialog
        assert dialog.add_field.x() < dialog.remove_field.x()
        assert dialog.form.labelForField(dialog.comment) is None
        before = dialog.form.rowCount()
        dialog.add_field.click()
        qtapp.processEvents()
        assert dialog.form.rowCount() == before + 1
        extra = dialog.extra_inputs[-1]
        assert dialog.orders[kind][:2] == [first, extra]
        assert dialog.comment.y() > extra.parentWidget().y()
        extra.setText("remove this text")
        dialog.remove_field.click()
        assert extra not in dialog.extra_inputs
        assert extra not in dialog.orders[kind]
        assert not extra.text()
        first.setFocus()
        qtapp.processEvents()
        first.setText("base value removed")
        dialog.remove_field.click()
        assert first not in dialog.orders[kind]
        assert not first.text()
        dialog.inputs["title"].setText("Synthetic")
        dialog.submit()
        saved = dialog.result_account
        restored = RecordDialog(None, [Service("s", "Test")], account=saved)
        try:
            assert first.accessibleName() not in [e.accessibleName() for e in restored.orders[kind]]
            assert document(parse(document(Snapshot([Service("s", "Test")], [saved])))) == document(Snapshot([Service("s", "Test")], [saved]))
        finally:
            restored.deleteLater()
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("kind", ["api", "account", "other"])
def test_extra_fields_editor_vault_exchange_and_copy(qtapp, tmp_path, kind):
    vault, _ = Vault.create(tmp_path / "fields.kdbx", "synthetic-passphrase-123")
    service = vault.service("Test").services[0]
    dialog = RecordDialog(None, [service], kind=kind)
    reopened_dialog = card = None
    try:
        dialog.inputs["title"].setText("Synthetic")
        dialog.show()
        dialog.orders[kind][0].setFocus()
        qtapp.processEvents()
        assert dialog.add_field.text() == "+"
        dialog.add_field.click()
        dialog.extra_inputs[0].setText("synthetic-extra")
        dialog.add_field.click()
        if kind == "other":
            base = dialog.all_inputs["other2"]
            dialog.show()
            base.setFocus()
            qtapp.processEvents()
            base.setText("deleted base text")
            dialog.remove_field.click()
        assert dialog.form.getWidgetPosition(dialog.comment)[0] == dialog.form.rowCount() - 1
        dialog.comment.setPlainText("comment stays last")
        dialog.submit()
        record = dialog.result_account
        assert [f.value for f in record.fields[-2:]] == ["synthetic-extra", ""]
        state = vault.account(record)
        vault.close()
        vault, state = Vault.open(tmp_path / "fields.kdbx", "synthetic-passphrase-123")
        record = state.accounts[0]
        if kind == "other":
            assert "Поле 2" not in record.field_layout
            assert not next(f.value for f in record.fields if f.label == "Поле 2")
        assert document(parse(document(state))) == document(state)
        reopened_dialog = RecordDialog(None, [service], account=record)
        assert [e.text() for e in reopened_dialog.extra_inputs] == ["synthetic-extra", ""]
        assert reopened_dialog.account.field_layout == record.field_layout
        assert [edit.accessibleName() for edit in reopened_dialog.orders[kind]] == record.field_layout
        copied = []
        card = AccountCard(record, copied.append, lambda a: None, lambda a: None)
        card.expand.click()
        assert [e.text() for e in card.body.findChildren(QLineEdit)] == ["synthetic-extra"]
        card.body.findChildren(Button)[0].click()
        assert copied == ["synthetic-extra"]
        reopened_dialog.scrub()
        assert all(not e.text() for e in reopened_dialog.extra_inputs)
    finally:
        vault.close()
        for widget in (dialog, reopened_dialog, card):
            if widget is not None:
                widget.deleteLater()


def test_extra_field_draft_survives_type_switch(qtapp):
    dialog = RecordDialog(None, [Service("s", "Test")], kind="api")
    try:
        dialog.add_field.click()
        dialog.extra_inputs[0].setText("draft")
        for kind in ("account", "other", "api"):
            dialog.record_type.setCurrentIndex(dialog.record_type.findData(kind))
            assert [edit.text() for edit in dialog.orders[kind]][:2] == ["", "draft"]
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("order", [["Unknown"], ["API-ключ", "API-ключ"], [], "API-ключ"])
def test_invalid_or_value_hiding_layout_is_rejected(qtapp, order):
    dialog = RecordDialog(None, [Service("s", "Test")], kind="api")
    try:
        dialog.inputs["title"].setText("Synthetic")
        dialog.inputs["key"].setText("synthetic-value")
        dialog.submit()
        data = document(Snapshot([Service("s", "Test")], [dialog.result_account]))
        data["services"][0]["records"][0]["field_layout"] = order
        with pytest.raises(ExchangeError):
            parse(data)
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("label", ["API-ключ", "Unknown", "Дополнительное поле 2"])
def test_extra_field_schema_rejects_duplicates_and_invalid_names(qtapp, label):
    dialog = RecordDialog(None, [Service("s", "Test")], kind="api")
    try:
        dialog.inputs["title"].setText("Synthetic")
        dialog.add_field.click()
        dialog.submit()
        data = document(Snapshot([Service("s", "Test")], [dialog.result_account]))
        data = copy.deepcopy(data)
        data["services"][0]["records"][0]["fields"][-1]["label"] = label
        with pytest.raises(ExchangeError):
            parse(data)
    finally:
        dialog.deleteLater()
