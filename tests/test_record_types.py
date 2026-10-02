import pytest
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit

from app.core.models import BASE_FIELD_LABELS, Account, Field, Service
from app.services.totp import current_code
from app.services.vault import Vault
from app.ui.cards import AccountCard
from app.ui.record_dialog import RecordDialog
from app.ui.widgets import Button
from tests.test_ui import make_window, process


@pytest.mark.parametrize("source,target", [(a, b) for a in ("api", "account", "other")
                                          for b in ("api", "account", "other") if a != b])
def test_type_conversion_transfers_visible_values_without_loss(qtapp, tmp_path, source, target):
    vault, _ = Vault.create(tmp_path / "transfer.kdbx", "synthetic-passphrase-123")
    service = vault.service("Test").services[0]
    dialog = RecordDialog(None, [service], kind=source)
    restored = None
    try:
        dialog.inputs["title"].setText("Transfer")
        dialog.comment.setPlainText("Keep notes")
        for edit, value in zip(dialog.orders[source], ["first", "second", "JBSWY3DPEHPK3PXP"], strict=False):
            edit.setText(value)
        dialog.active_input = dialog.orders[source][0]
        dialog.add_empty_field(value="inserted", focus=False)
        dialog.active_input = None
        dialog.add_empty_field(value="last", focus=False)
        values = [edit.text() for edit in dialog.orders[source]]
        # Keep the third value a valid TOTP when converting into an account.
        if target == "account":
            dialog.orders[source][2].setText("JBSWY3DPEHPK3PXP")
            values[2] = "JBSWY3DPEHPK3PXP"
        for kind in (target, source, target):
            dialog.record_type.setCurrentIndex(dialog.record_type.findData(kind))
            assert [edit.text() for edit in dialog.orders[kind]] == values
            assert all(not edit.parentWidget().isHidden() for edit in dialog.orders[kind])
        assert dialog.inputs["title"].text() == "Transfer"
        assert dialog.comment.toPlainText() == "Keep notes"
        dialog.submit()
        assert dialog.result_account is not None
        vault.account(dialog.result_account)
        vault.close()
        vault, state = Vault.open(tmp_path / "transfer.kdbx", "synthetic-passphrase-123")
        restored = RecordDialog(None, [service], account=state.accounts[0])
        assert [edit.text() for edit in restored.orders[target]] == values
    finally:
        vault.close()
        dialog.deleteLater()
        if restored is not None:
            restored.deleteLater()


@pytest.mark.parametrize("source,target", [("api", "account"), ("account", "other"), ("other", "api")])
def test_existing_record_type_change_save_and_reopen(qtapp, tmp_path, source, target):
    vault, _ = Vault.create(tmp_path / "convert.kdbx", "synthetic-passphrase-123")
    service = vault.service("Test").services[0]
    original = Account(service_id=service.id, title="Synthetic", kind=source, favorite=True, notes="Keep comment",
                       fields=[Field(name, "") for name in BASE_FIELD_LABELS[source]] +
                              [Field("Дополнительное поле 1", "Keep extra")])
    original = vault.account(original).accounts[0]
    dialog = RecordDialog(None, [service], account=original)
    try:
        assert dialog.record_type.isEnabled()
        dialog.record_type.setCurrentIndex(dialog.record_type.findData(target))
        assert set(dialog.inputs) == set({"api": ["title", "key"], "account": ["title", "login", "password", "totp"],
                                          "other": ["title", "other1", "other2", "other3"]}[target])
        assert dialog.paid.isHidden() == (target != "api")
        key = {"api": "key", "account": "login", "other": "other1"}[target]
        dialog.inputs[key].setText("New type value")
        dialog.record_type.setCurrentIndex(dialog.record_type.findData(source))
        dialog.record_type.setCurrentIndex(dialog.record_type.findData(target))
        assert dialog.inputs[key].text() == "New type value"
        dialog.submit()
        changed = dialog.result_account
        assert changed.id == original.id and changed.kind == target
        assert changed.favorite and changed.notes == "Keep comment"
        assert "Keep extra" in [changed.login, *(field.value for field in changed.fields)]
        state = vault.account(changed)
        vault.close()
        vault, reopened = Vault.open(tmp_path / "convert.kdbx", "synthetic-passphrase-123")
        assert reopened == state and len(reopened.accounts) == 1
        card = AccountCard(reopened.accounts[0], lambda value: None, lambda a: None, lambda a: None)
        assert card.property("recordKind") == target
        card.deleteLater()
    finally:
        dialog.deleteLater()
        vault.close()


def test_totp_reference_and_invalid_input():
    # RFC 6238 SHA1 test vector at 59 seconds, six digit truncation.
    seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert current_code(seed, 59) == ("287082", 1)
    assert current_code(seed, 60)[1] == 30
    assert current_code(f"otpauth://totp/test?secret={seed}&digits=8", 59)[0] == "94287082"
    for invalid in ["not-a-secret!", "otpauth://hotp/test?secret=JBSWY3DPEHPK3PXP&counter=0", "otpauth://totp/test?secret=JBSWY3DPEHPK3PXP&period=0"]:
        with pytest.raises(ValueError):
            current_code(invalid)


def test_exact_fields_and_validation(qtapp):
    services = [Service("synthetic", "Service")]
    api = RecordDialog(None, services, kind="api")
    account = RecordDialog(None, services)
    try:
        assert set(api.inputs) == {"key", "title"}
        assert api.findChildren(QComboBox) == [api.record_type]
        assert api.record_type.currentData() == "api"
        assert len(account.inputs) == 4
        assert all(e.echoMode() == QLineEdit.EchoMode.Normal for e in account.inputs.values())
        api.inputs["title"].setText("Production")
        api.inputs["key"].setText("synthetic-key")
        api.comment.setPlainText("Long\ncomment")
        api.submit()
        assert api.result_account.kind == "api"
        assert api.result_account.notes == "Long\ncomment"
        assert list(account.inputs) == ["title", "login", "password", "totp"]
        account.inputs["title"].setText("Work")
        account.comment.setPlainText("Account\ncomment")
        account.inputs["login"].setText("test@example.invalid")
        account.inputs["totp"].setText("invalid!")
        account.submit()
        assert account.result() != QDialog.DialogCode.Accepted
        account.inputs["totp"].clear()
        account.submit()
        assert account.result_account.kind == "account"
        assert account.result_account.title == "Work"
        assert account.result_account.notes == "Account\ncomment"
    finally:
        for dialog in [api, account]:
            dialog.scrub()
            assert all(not edit.text() for edit in dialog.inputs.values())
            dialog.deleteLater()


def test_roundtrip_types_and_legacy_preserved(tmp_path):
    path = tmp_path / "types.kdbx"
    vault, _ = Vault.create(path, "synthetic-passphrase-123")
    try:
        state = vault.service("Test")
        service = state.services[0]
        for a in [Account(service_id=service.id, title="API", kind="api", notes="comment", fields=[Field("API-ключ", "synthetic-key")]),
                  Account(service_id=service.id, title="login", login="login", kind="account", fields=[Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "JBSWY3DPEHPK3PXP")]),
                  Account(service_id=service.id, title="No 2FA", kind="account", login="optional", fields=[Field("Пароль", ""), Field("Секрет 2FA", "")]),
                  Account(service_id=service.id, title="Old", project="keep", fields=[Field("Extra", "keep-secret")])]:
            state = vault.account(a)
        vault.close()
        vault, reopened = Vault.open(path, "synthetic-passphrase-123")
        assert reopened == state
        assert {a.kind for a in reopened.accounts} == {"legacy", "api", "account"}
        legacy = next(a for a in reopened.accounts if a.kind == "legacy")
        assert legacy.project == "keep" and legacy.fields[0].value == "keep-secret"
        assert b"synthetic-key" not in path.read_bytes()
    finally:
        vault.close()


def test_star_filter_persistence_and_totp_lock(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        card = window.cards[0]
        card.favorite_button.click()
        process(qtapp, lambda: not window.busy)
        assert window.snapshot.accounts[0].favorite
        window.vault_tab.favorites.setChecked(True)
        assert len(window.cards) == 1
        window.cards[0].favorite_button.click()
        process(qtapp, lambda: not window.busy)
        assert not window.cards
        window.vault_tab.favorites.setChecked(False)
        assert len(window.cards) == 1
        a = Account(service_id=window.current_service(), title="2FA", login="2FA", kind="account", fields=[Field("Пароль", "synthetic"), Field("Секрет 2FA", "JBSWY3DPEHPK3PXP")])
        window.saved(window.vault.account(a))
        card = next(c for c in window.cards if c.account.kind == "account")
        card.expand.click()
        assert len(card.totp.code()) == 6
        assert card.totp.text() == card.totp.code()
        window.lock()
        assert not card.totp.secret
        assert not card.totp.refresh_timer.isActive()
    finally:
        window.exit_application()


def test_compact_cards_show_values_and_copy(qtapp):
    copied = []
    for account, expected in [
        (Account(title="API", service="Hidden service", kind="api", notes="Hidden comment", fields=[Field("API-ключ", "synthetic-key")]), ["synthetic-key"]),
        (Account(title="login", login="login", kind="account", fields=[Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "JBSWY3DPEHPK3PXP")]), ["login", "synthetic-password"]),
    ]:
        card = AccountCard(account, copied.append, lambda a: None, lambda a: None)
        try:
            card.expand.click()
            edits = card.body.findChildren(QLineEdit)
            assert [e.text() for e in edits[:len(expected)]] == expected
            assert all(e.isReadOnly() and e.echoMode() == QLineEdit.EchoMode.Normal for e in edits)
            buttons = card.body.findChildren(Button)
            assert all(b.text() == "Копировать" for b in buttons)
            for button, value in zip(buttons, expected, strict=False):
                button.click()
                assert copied[-1] == value
            if account.kind == "api":
                assert len(edits) == len(buttons) == 1
            else:
                assert len(edits) == len(buttons) == 3
                card.expand.click()
                assert not card.totp.refresh_timer.isActive()
                assert not card.totp.text()
            card.scrub()
            assert all(not e.text() for e in edits)
        finally:
            card.deleteLater()


@pytest.mark.parametrize("account, expected", [
    (Account(kind="api", fields=[Field("API-ключ", "")]), []),
    (Account(kind="account", login="", fields=[Field("Пароль", "x"), Field("Секрет 2FA", "")]), ["x"]),
    (Account(kind="account", login="x", fields=[Field("Пароль", ""), Field("Секрет 2FA", "")]), ["x"]),
    (Account(kind="other", fields=[Field("Поле 1", ""), Field("Поле 2", "x"), Field("Поле 3", "")]), ["x"]),
    (Account(kind="other", fields=[Field("Поле 1", " "), Field("Поле 2", ""), Field("Поле 3", "")]), [" "]),
    (Account(kind="legacy", fields=[Field("Пустое поле", "")]), []),
])
def test_empty_fields_are_absent_from_accordion(qtapp, account, expected):
    copied = []
    card = AccountCard(account, copied.append, lambda a: None, lambda a: None)
    try:
        card.expand.click()
        assert [edit.text() for edit in card.body.findChildren(QLineEdit)] == expected
        buttons = [button for button in card.body.findChildren(Button) if button.text() == "Копировать"]
        assert len(buttons) == len(expected)
        for button in buttons:
            button.click()
        assert copied == expected
        assert all(widget.accessibleName() != "Пустое поле" for widget in card.body.findChildren(QLineEdit))
    finally:
        card.scrub()
        card.deleteLater()


def test_type_filters_combine_with_search_and_favorites(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        service = window.current_service()
        for kind, favorite in [("api", True), ("account", False)]:
            window.saved(window.vault.account(Account(service_id=service, title="Typed " + kind, kind=kind, favorite=favorite)))
        tab = window.vault_tab
        assert len(window.cards) == 3
        tab.filter_api.click()
        assert [c.account.kind for c in window.cards] == ["api"]
        tab.filter_account.click()
        assert len(window.cards) == 3
        tab.filter_api.click()
        assert {c.account.kind for c in window.cards} == {"account", "legacy"}
        tab.filter_account.click()
        assert len(window.cards) == 3
        tab.search.setText("Typed")
        assert len(window.cards) == 2
        tab.favorites.click()
        assert [c.account.kind for c in window.cards] == ["api"]
        tab.filter_account.click()
        assert not window.cards
        tab.filter_api.click()
        assert len(window.cards) == 1
    finally:
        window.exit_application()


def test_paid_api_edit_badge_and_reopen(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        dialog = RecordDialog(window, window.snapshot.services, service_id=window.current_service(), kind="api")
        dialog.inputs["title"].setText("Paid API")
        dialog.inputs["key"].setText("synthetic-paid-key")
        assert not dialog.paid.isChecked()
        assert dialog.paid.text() == "⓪"
        dialog.paid.click()
        assert dialog.paid.isChecked() and dialog.paid.text() == "$"
        dialog.submit()
        record = dialog.result_account
        assert record.api_paid
        dialog.scrub()
        dialog.deleteLater()
        window.saved(window.vault.account(record))
        card = next(c for c in window.cards if c.account.kind == "api")
        from PySide6.QtWidgets import QLabel
        assert card.findChild(QLabel, "apiPaid").text() == "$"
        qtapp.processEvents()
        assert card.quick_copy.width() == card.quick_copy.height()
        assert not card.expand.isChecked()
        card.quick_copy.click()
        assert qtapp.clipboard().text() == "synthetic-paid-key"
        assert not card.expand.isChecked()
        window.lock()
        vault, state = Vault.open(window.path, "synthetic-test-passphrase-123")
        window.opened((vault, state))
        record = next(a for a in state.accounts if a.kind == "api")
        assert record.api_paid
        dialog = RecordDialog(window, state.services, record)
        assert dialog.paid.isChecked()
        assert dialog.paid.text() == "$"
        dialog.paid.click()
        assert not dialog.paid.isChecked() and dialog.paid.text() == "⓪"
        dialog.submit()
        window.saved(vault.account(dialog.result_account))
        card = next(c for c in window.cards if c.account.kind == "api")
        assert card.findChild(QLabel, "apiPaid") is None
        assert card.findChild(QLabel, "apiFree").text() == "⓪"
        dialog.scrub()
        dialog.deleteLater()
    finally:
        window.exit_application()


def test_unified_add_other_roundtrip_edit_and_copy(qtapp, tmp_path):
    from PySide6.QtCore import QTimer

    from app.services.exchange import document, parse

    window = make_window(qtapp, tmp_path)
    try:
        tab = window.vault_tab
        assert tab.add_record.text() == "+"
        assert not hasattr(tab, "add_api") and not hasattr(tab, "add_account")

        failures = []

        def fill_dialog():
            try:
                fill_fields()
            except Exception as error:
                failures.append(error)
                window.dialogs[-1].reject()

        def fill_fields():
            dialog = window.dialogs[-1]
            assert isinstance(dialog, RecordDialog)
            dialog.inputs["title"].setText("Other record")
            dialog.inputs["password"].setText("account draft")
            dialog.record_type.setCurrentIndex(dialog.record_type.findData("api"))
            dialog.inputs["key"].setText("api draft")
            dialog.paid.setChecked(True)
            dialog.record_type.setCurrentIndex(dialog.record_type.findData("other"))
            assert dialog.inputs["title"].text() == "Other record"
            assert list(dialog.inputs) == ["title", "other1", "other2", "other3"]
            assert not dialog.paid.isVisible()
            for i in range(1, 4):
                dialog.inputs[f"other{i}"].setText(f"synthetic value {i}")
                caption = dialog.form.labelForField(dialog.inputs[f"other{i}"])
                assert caption is None or caption.text() == ""
            assert dialog.form.getWidgetPosition(dialog.comment)[0] == dialog.form.rowCount() - 1
            dialog.comment.setPlainText("Other comment\nlast")
            dialog.submit()

        QTimer.singleShot(0, fill_dialog)
        tab.add_record.click()
        assert not failures, str(failures)
        process(qtapp, lambda: not window.busy)
        record = next(a for a in window.snapshot.accounts if a.kind == "other")
        assert record.login == "" and not record.api_paid
        assert [f.value for f in record.fields] == [f"synthetic value {i}" for i in range(1, 4)]
        assert record.notes == "Other comment\nlast"
        assert document(parse(document(window.snapshot))) == document(window.snapshot)
        tab.filter_other.click()
        assert [c.account.kind for c in window.cards] == ["other"]
        card = window.cards[0]
        assert card.property("recordKind") == "other"
        assert not card.expand.isChecked()
        card.quick_copy.click()
        assert qtapp.clipboard().text() == "synthetic value 1"
        assert not card.expand.isChecked()
        assert card.quick_copy.accessibleName() == "Скопировано"
        card.expand.click()
        edits = card.body.findChildren(QLineEdit)
        assert [e.text() for e in edits] == [f.value for f in record.fields]
        assert all(not e.placeholderText() for e in edits)
        card.body.findChildren(Button)[2].click()
        assert qtapp.clipboard().text() == "synthetic value 3"
        path = window.path
        window.lock()
        assert all(not e.text() for e in edits)
        vault, state = Vault.open(path, "synthetic-test-passphrase-123")
        window.opened((vault, state))
        reopened = next(a for a in state.accounts if a.kind == "other")
        assert reopened == record
        dialog = RecordDialog(window, state.services, reopened)
        assert dialog.record_type.currentData() == "other" and dialog.record_type.isEnabled()
        dialog.inputs["other2"].setText("updated")
        dialog.submit()
        window.saved(vault.account(dialog.result_account))
        dialog.scrub()
        assert all(not e.text() for e in dialog.all_inputs.values())
        dialog.deleteLater()
        assert window.cards[0].account.fields[1].value == "updated"
    finally:
        window.exit_application()
