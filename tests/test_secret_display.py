import pytest
from PySide6.QtWidgets import QLineEdit

from app.core.models import Account, Field, Service
from app.core.settings import Settings
from app.ui.cards import AccountCard
from app.ui.dialogs import FieldEditor
from app.ui.record_dialog import RecordDialog
from tests.test_ui import make_window


@pytest.mark.parametrize("hidden", [True, False])
@pytest.mark.parametrize("kind,caption", [("api", "API-ключ"), ("account", "Пароль"),
                                         ("other", "Поле 1")])
def test_display_policy_preserves_values_and_copy(qtapp, hidden, kind, caption):
    record = Account(service_id="s", title="Synthetic", login="synthetic-login",
                     kind=kind, fields=[Field(caption, "synthetic-secret")])
    copied = []
    card = AccountCard(record, copied.append, lambda _: None, lambda _: None,
                       hide_record_secrets=hidden)
    mode = QLineEdit.EchoMode.Password if hidden and kind != "other" else QLineEdit.EchoMode.Normal
    try:
        edit = next(e for e in card.body.findChildren(QLineEdit) if e.accessibleName() == caption)
        assert edit.echoMode() == mode
        assert edit.text() == "synthetic-secret"
        if mode == QLineEdit.EchoMode.Password:
            assert "synthetic" not in edit.displayText()
        card.copy_button(lambda: copied.append(edit.text()), "Copy").click()
        assert copied == ["synthetic-secret"]
        assert record.fields[0].secret
    finally:
        card.scrub()
        card.deleteLater()


def test_toggle_persists_and_editor_obeys_setting(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        control = window.system_tab.hide_record_secrets
        assert control.isChecked()
        for hidden in (False, True):
            control.setChecked(hidden)
            assert Settings(window.settings.path).data["hide_record_secrets"] is hidden
            dialog = RecordDialog(window, [Service("s", "Synthetic")], kind="api")
            try:
                mode = QLineEdit.EchoMode.Password if hidden else QLineEdit.EchoMode.Normal
                assert dialog.inputs["key"].echoMode() == mode
                dialog.record_type.setCurrentIndex(dialog.record_type.findData("other"))
                assert all(e.echoMode() == QLineEdit.EchoMode.Normal for e in dialog.orders["other"])
                dialog.record_type.setCurrentIndex(dialog.record_type.findData("account"))
                assert dialog.inputs["password"].echoMode() == mode
                assert dialog.inputs["login"].echoMode() == QLineEdit.EchoMode.Normal
                legacy = FieldEditor(Field("Secret", "synthetic"), lambda _: None, hidden)
                assert legacy.value.echoMode() == mode
                assert legacy.field().secret
                legacy.scrub()
                legacy.deleteLater()
            finally:
                dialog.scrub()
                dialog.deleteLater()
    finally:
        window.exit_application()
