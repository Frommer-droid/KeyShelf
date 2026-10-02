import time

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QMessageBox, QStyle, QStyleOptionButton

from app.core.models import Account, Field
from app.core.settings import Settings
from app.services.clipboard import Clipboard
from app.services.vault import Vault
from app.ui.dialogs import AccountDialog
from app.ui.main_window import MainWindow
from app.ui.theme import THEME_COLORS
from app.ui.widgets import Button

PASSWORD = "synthetic-test-passphrase-123"


def process(qtapp, condition=lambda: True, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qtapp.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Qt operation timed out")


def make_window(qtapp, tmp_path):
    window = MainWindow(Settings(tmp_path / "settings.json"))
    vault, state = Vault.create(tmp_path / "synthetic.kdbx", PASSWORD)
    state = vault.service("OpenAI")
    service = next(s for s in state.services if s.name == "OpenAI")
    state = vault.account(Account(service_id=service.id, title="Основной аккаунт",
                                  login="work@example.invalid", project="Тестовый проект",
                                  fields=[Field("API-ключ", "synthetic-ui-secret"),
                                          Field("Тестовый ключ", "synthetic-ui-second")]))
    window.opened((vault, state))
    window.show()
    process(qtapp)
    return window


def test_clipboard_ownership_without_timer(qtapp):
    clip = Clipboard(qtapp.clipboard())
    clip.copy("synthetic-copy")
    qtapp.clipboard().setText("foreign-new-text")
    clip.clear_owned()
    assert qtapp.clipboard().text() == "foreign-new-text"
    clip.copy("same")
    qtapp.clipboard().setText("same")
    clip.clear_owned()
    assert qtapp.clipboard().text() == "same"
    qtapp.clipboard().clear()


def test_cards_copy_reveal_lock(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    card = window.cards[0]
    try:
        assert not card.body.isVisible()
        card.expand.click()
        assert card.body.isVisible()
        secret = card.values[0]
        assert "synthetic" not in secret.text()
        secret.toggle()
        assert secret.text() == "synthetic-ui-secret"
        secret.toggle()
        assert "synthetic" not in secret.text()
        window.copy_value("synthetic-ui-secret")
        assert qtapp.clipboard().text() == "synthetic-ui-secret"
        window.lock()
        assert window.vault is None
        assert not window.snapshot.accounts
        assert not window.cards
        assert not card.values[0].value
        assert qtapp.clipboard().text() == ""
        assert window.stack.currentIndex() == 0
    finally:
        window.exit_application()


def test_dialog_crud_and_lock_scrubs_editor(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        account = window.snapshot.accounts[0]
        dialog = AccountDialog(window, window.snapshot.services, account)
        dialog.inputs["title"].setText("Изменённый аккаунт")
        dialog.add_field(Field("Новый ключ", "synthetic-added"))
        dialog.submit()
        assert dialog.result() == QDialog.DialogCode.Accepted
        state = window.vault.account(dialog.result_account)
        assert state.accounts[0].title == "Изменённый аккаунт"
        assert len(state.accounts[0].fields) == 3
        dialog.scrub()
        dialog.deleteLater()
        dialog = AccountDialog(window, state.services, state.accounts[0])
        window.dialogs.append(dialog)
        dialog.show()
        window.lock()
        assert dialog.account is None
        assert all(not row.value.text() for row in dialog.rows)
        assert not dialog.isVisible()
        window.dialogs.remove(dialog)
        dialog.deleteLater()
    finally:
        window.exit_application()


def test_async_mutation_manual_lock_and_late_unlock(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        vault = window.vault
        window.run_job(lambda: vault.service("Google"), window.saved)
        process(qtapp, lambda: not window.busy)
        assert any(s.name == "Google" for s in window.snapshot.services)
        window.lock()
        assert not window.vault
        window.run_job(lambda: Vault.open(window.path, PASSWORD), window.opened)
        window.lock()
        process(qtapp, lambda: not window.busy)
        assert not window.vault
        reopened, _ = Vault.open(window.path, PASSWORD)
        reopened.close()
    finally:
        window.exit_application()


def test_lock_during_save_closes_pending_vault(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        vault = window.vault
        window.run_job(lambda: vault.service("Saved during lock"), window.saved)
        window.lock()
        assert not window.snapshot.accounts
        process(qtapp, lambda: not window.busy)
        assert window.pending_vault is None
        assert not vault.password
        assert not window.vault
        assert window.stack.currentIndex() == 0
        reopened, state = Vault.open(window.path, PASSWORD)
        assert any(s.name == "Saved during lock" for s in state.services)
        reopened.close()
    finally:
        window.exit_application()


def test_confirm_default_cancel_and_search(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        QTimer.singleShot(0, lambda: next(d for d in window.dialogs if isinstance(d, QMessageBox)).reject())
        assert not window.confirm("Синтетическое удаление")
        window.vault_tab.search.setText("synthetic-ui-secret")
        assert not window.cards
        window.vault_tab.search.setText("openai проект")
        assert len(window.cards) == 1
        window.resize(940, 650)
        process(qtapp)
        assert window.vault_tab.add_record.isVisible()
        # Стандартное контекстное меню Qt переведено до создания полей.
        menu = window.vault_tab.search.createStandardContextMenu()
        assert any("Копировать" in action.text() for action in menu.actions())
        menu.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    finally:
        window.exit_application()


def test_delete_button_role_states(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.cards[0].expand.click()
        process(qtapp)
        button = next(b for b in window.cards[0].findChildren(Button) if b.objectName() == "danger_btn")
        assert button.isEnabled()
        assert button.isVisible()
        # Qt рисует настоящие QSS-состояния в pixmap; курсор пользователя не влияет.
        def pixel(state):
            option = QStyleOptionButton()
            option.initFrom(button)
            option.text = button.text()
            option.state = state
            pixmap = QPixmap(button.size())
            painter = QPainter(pixmap)
            button.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, button)
            painter.end()
            # Sample padding, away from the text even at reduced UI scales.
            return pixmap.toImage().pixelColor(4, button.height() // 2).name().upper()
        assert pixel(QStyle.StateFlag.State_Enabled) == THEME_COLORS["danger"]
        assert pixel(QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver) == THEME_COLORS["danger_text"]
        button.setEnabled(False)
        assert pixel(QStyle.StateFlag.State_None) == THEME_COLORS["disabled_background"]
        button.setEnabled(True)
    finally:
        window.exit_application()


def test_global_search_and_service_selection(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.saved(window.vault.service("Other"))
        other = next(s for s in window.snapshot.services if s.name == "Other")
        window.saved(window.vault.account(Account(service_id=other.id, title="Other account", kind="account")))
        tab = window.vault_tab
        tab.search.setText("Other account")
        assert len(window.cards) == 1
        assert window.cards[0].account.service_id == other.id
        assert "Результаты во всех сервисах" in tab.heading.text()
        # Clicking the already selected service also clears global search.
        tab.services.itemClicked.emit(tab.services.currentItem())
        assert not tab.search.text()
        assert len(window.cards) == 1
        assert window.cards[0].account.service_id != other.id
        tab.search.setText("Основной")
        tab.services.setCurrentRow(1)
        assert not tab.search.text()
        assert window.cards[0].account.service_id == other.id
        assert not hasattr(tab, "scope")
    finally:
        window.exit_application()
