"""Активация кнопок и скруглённое выделение клавиатурного фокуса."""

import pytest
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QVBoxLayout

from app.core.models import Account, Field
from app.ui.cards import AccountCard
from app.ui.widgets import Button, CopyIconButton, FavoriteButton


@pytest.mark.parametrize("key,modifiers", [
    (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier),
    (Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier),
])
@pytest.mark.parametrize("kind", ["normal", "copy", "favorite", "accordion"])
def test_focused_button_activates_once(qtapp, key, modifiers, kind):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    clicks = []
    defaults = []
    default = Button("Сохранить", lambda: defaults.append(True), "success_btn")
    default.setDefault(True)
    layout.addWidget(default)
    if kind == "copy":
        button = CopyIconButton(lambda: qtapp.clipboard().setText("synthetic-copy-enter"),
                                "Копировать тестовое поле")
    elif kind == "favorite":
        button = FavoriteButton()
    elif kind == "accordion":
        card = AccountCard(Account(title="Тест", kind="api",
                                   fields=[Field("API-ключ", "synthetic-key")]),
                           lambda *_: None, lambda *_: None, lambda *_: None, compact=True)
        layout.addWidget(card)
        button = card.expand
    else:
        button = Button("Отмена")
    if kind != "accordion":
        layout.addWidget(button)
    button.clicked.connect(lambda: clicks.append(True))
    try:
        dialog.show()
        button.setFocus()
        qtapp.processEvents()
        QTest.keyClick(button, key, modifiers)
        assert clicks == [True]
        assert not defaults
        if kind == "copy":
            assert qtapp.clipboard().text() == "synthetic-copy-enter"
            assert button.text() == "✓"
        elif kind == "favorite":
            assert button.isChecked()
        elif kind == "accordion":
            assert card.body.isVisible()
    finally:
        if kind == "copy":
            qtapp.clipboard().clear()
        dialog.close()
        dialog.deleteLater()


def test_enter_autorepeat_and_disabled_button_do_not_click(qtapp):
    button = Button("Проверка")
    clicks = []
    button.clicked.connect(lambda: clicks.append(True))
    try:
        button.show()
        button.setFocus()
        qtapp.processEvents()
        repeat = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return,
                           Qt.KeyboardModifier.NoModifier, "", True)
        QCoreApplication.sendEvent(button, repeat)
        assert not clicks
        button.setEnabled(False)
        QTest.keyClick(button, Qt.Key.Key_Return)
        assert not clicks
    finally:
        button.close()
        button.deleteLater()
