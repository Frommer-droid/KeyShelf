import copy

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QCheckBox,
    QPushButton,
    QScrollArea,
    QScroller,
    QStyle,
    QStyleOptionComboBox,
)

from app.core.models import Account, Field, Service
from app.ui.dialogs import AccountDialog
from app.ui.record_dialog import RecordDialog
from tests.test_mini_mode import settle


@pytest.mark.parametrize("kind", ["account", "api", "other", "legacy"])
def test_long_editor_accepts_touch_scroll_and_keeps_save_visible(qtapp, kind):
    fields = [Field(f"Дополнительное поле {i}", "synthetic") for i in range(1, 31)]
    account = Account(service_id="synthetic", title="Synthetic", kind=kind, fields=fields)
    services = [Service("synthetic", "Synthetic")]
    editor = AccountDialog(None, services, account) if kind == "legacy" else RecordDialog(None, services, account)
    try:
        editor.show()
        settle(qtapp)
        area = editor.findChild(QScrollArea)
        bar = area.verticalScrollBar()
        assert bar.maximum() > 0
        scroller = QScroller.scroller(area.viewport())
        assert QScroller.grabbedGesture(area.viewport()) != 0
        bar.setValue(0)
        start = QPointF(area.viewport().width() / 2, area.viewport().height() * .75)
        scroller.handleInput(QScroller.Input.InputPress, start, 1000)
        scroller.handleInput(QScroller.Input.InputMove, start - QPointF(0, 50), 1100)
        scroller.handleInput(QScroller.Input.InputMove, start - QPointF(0, 150), 1200)
        QTest.qWait(100)
        assert bar.value() > 0
        scroller.handleInput(QScroller.Input.InputRelease, start - QPointF(0, 150), 1300)
        scroller.stop()
        save = next(button for button in editor.findChildren(QPushButton) if button.text() == "Сохранить")
        assert save.isVisibleTo(editor)
        assert editor.rect().contains(save.mapTo(editor, save.rect().bottomRight()))
        assert editor.result_account is None and account.title == "Synthetic"
    finally:
        editor.scrub()
        editor.close()


@pytest.mark.parametrize("kind", ["account", "api", "other", "legacy"])
def test_editor_actions_equal_width_cursor_insert_and_favorite_draft(qtapp, tmp_path, kind):
    fields = {"account": [Field("Пароль", "first"), Field("Секрет 2FA", "")],
              "api": [Field("API-ключ", "first"), Field("Дополнительное поле 1", "tail")],
              "other": [Field(f"Поле {i}", f"value-{i}") for i in range(1, 4)],
              "legacy": [Field("First", "first"), Field("Second", "tail")]}
    account = Account(service_id="synthetic", title="Synthetic", kind=kind, fields=fields[kind])
    original = copy.deepcopy(account)
    services = [Service("synthetic", "Synthetic service")]
    editor = AccountDialog(None, services, account) if kind == "legacy" else RecordDialog(None, services, account)
    try:
        editor.show()
        editor.activateWindow()
        settle(qtapp)
        assert editor.form.getWidgetPosition(editor.service_selector)[0] == 0
        assert editor.form.getWidgetPosition(editor.record_type.parentWidget() if kind != "legacy" else editor.record_type)[0] == 1
        add = editor.add_field_button if kind == "legacy" else editor.add_field
        assert add.parent() is editor.favorite.parent()
        assert abs(add.width() - editor.favorite.width()) <= 1
        assert add.height() == editor.favorite.height()
        assert not any("Избран" in check.text() for check in editor.findChildren(QCheckBox))
        assert editor.favorite.text() == "☆"
        editor.favorite.click()
        assert editor.favorite.isChecked() and editor.favorite.text() == "★"
        assert account == original
        first = editor.rows[0].value if kind == "legacy" else editor.all_inputs["password"] if kind == "account" else editor.orders[kind][0]
        first.setFocus()
        settle(qtapp)
        add.click()
        settle(qtapp)
        order = [row.value for row in editor.rows] if kind == "legacy" else editor.orders[kind]
        inserted = order[order.index(first) + 1]
        assert inserted.hasFocus()
        inserted.setText("inserted-middle")
        if kind == "legacy":
            assert editor.field_layout.spacing() == 8
            assert all(row.height() == row.value.height() for row in editor.rows)
        else:
            assert editor.form.verticalSpacing() == 8
            assert editor.form.getWidgetPosition(editor.field_actions)[0] + 1 == editor.form.getWidgetPosition(editor.comment)[0]
        option = QStyleOptionComboBox()
        editor.service.initStyleOption(option)
        arrow = editor.service.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                                     QStyle.SubControl.SC_ComboBoxArrow, editor.service)
        assert arrow.right() >= editor.service.width() - 3
        editor.grab().save(str(tmp_path / f"editor-{kind}.png"))
        editor.submit()
        result = editor.result_account
        assert result.favorite
        visible = result.fields if kind == "legacy" else [f for name in result.field_layout for f in result.fields if f.label == name]
        assert visible[0].value == original.fields[0].value
        assert visible[1].value == "inserted-middle"
        assert account == original
    finally:
        editor.scrub()
        editor.close()


@pytest.mark.parametrize("kind", ["account", "api", "other", "legacy"])
def test_editor_favorite_cancel_keeps_original(qtapp, kind):
    account = Account(service_id="synthetic", title="Synthetic", kind=kind, favorite=True)
    services = [Service("synthetic", "Synthetic")]
    editor = AccountDialog(None, services, account) if kind == "legacy" else RecordDialog(None, services, account)
    try:
        assert editor.favorite.isChecked()
        editor.favorite.click()
        editor.reject()
        assert account.favorite and editor.result_account is None
    finally:
        editor.scrub()
        editor.close()
