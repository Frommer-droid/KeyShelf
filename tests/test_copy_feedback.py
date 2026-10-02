from PySide6.QtTest import QTest

from app.core.models import Account, Field
from app.ui.cards import AccountCard
from tests.test_ui import process


def test_copy_confirmation_repeat_reset_and_scrub(qtapp):
    copied = []
    account = Account(title="Synthetic", kind="other", fields=[Field("Поле 1", "synthetic-first")])
    card = AccountCard(account, copied.append, lambda a: None, lambda a: None)
    try:
        card.show()
        qtapp.processEvents()
        button = card.quick_copy
        size = button.size()
        assert button.text() == "⧉"
        button.click()
        assert copied == ["synthetic-first"] and button.text() == "✓"
        assert not card.expand.isChecked() and button.size() == size
        QTest.qWait(700)
        button.click()
        QTest.qWait(700)
        assert copied == ["synthetic-first", "synthetic-first"] and button.text() == "✓"
        process(qtapp, lambda: not button.reset_timer.isActive())
        assert button.text() == "⧉" and button.accessibleName() == "Копировать первое поле"
        button.click()
        card.scrub()
        assert not button.reset_timer.isActive() and button.text() == ""
        assert button.callback is None
    finally:
        card.close()
        card.deleteLater()


def test_declined_copy_has_no_confirmation(qtapp):
    account = Account(title="API", kind="api", fields=[Field("API-ключ", "synthetic")])
    card = AccountCard(account, lambda value: False, lambda a: None, lambda a: None)
    try:
        card.quick_copy.click()
        assert card.quick_copy.text() == "⧉" and not card.quick_copy.reset_timer.isActive()
    finally:
        card.scrub()
        card.deleteLater()
