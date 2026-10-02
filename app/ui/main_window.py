import copy
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
)

from app.core.models import Snapshot, search
from app.core.settings import Settings, default_vault_path, validate_vault_path
from app.services.autostart import Autostart
from app.services.clipboard import Clipboard
from app.services.exchange import ExchangeError, read_exchange, write_exchange
from app.services.vault import Vault
from app.services.worker import Job
from app.ui.cards import AccountCard
from app.ui.dialogs import AccountDialog, PasswordDialog
from app.ui.record_dialog import RecordDialog
from app.ui.tray import Tray
from app.ui.ui_scale_overrides import metrics
from app.ui.ui_scale_runtime import UIScaleRuntime
from app.ui.view_mode import ViewMode
from app.ui.widgets import label
from app.ui.window_shell import build_shell
from app.ui.window_signals import connect_signals


class MainWindow(QMainWindow):
    def __init__(self, settings=None, autostart=None):
        super().__init__()
        self.setWindowIcon(QApplication.windowIcon())
        self.setWindowTitle("KeyShelf")
        self.setMinimumSize(940, 650)
        self.settings = settings or Settings()
        self.autostart = autostart or Autostart()
        self.startup_pending = False
        self.vault = None
        self.snapshot = Snapshot()
        self.path = None
        self.cards = []
        self.dialogs = []
        self.busy = False
        self.epoch = 0
        self.closing = False
        self.exiting = False
        self.in_tray = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.job = None
        self.callback = None
        self.job_epoch = 0
        self.pending_vault = None
        self.clipboard = Clipboard(QApplication.clipboard(), self)
        build_shell(self)
        self.settings.data["autostart_enabled"] = self.autostart.enabled()
        self.system_tab.autostart.setChecked(self.settings.data["autostart_enabled"])
        self.system_tab.start_minimized.setChecked(self.settings.data["start_minimized"])
        connect_signals(self)
        self.restore_geometry()
        self.geometry_timer = QTimer(self)
        self.geometry_timer.setSingleShot(True)
        self.geometry_timer.timeout.connect(self.save_geometry)
        self.tray = Tray(self)
        self.refresh_recent()
        self.update_controls()
        self.ui_scale = UIScaleRuntime(self)
        self.view_mode = ViewMode(self)

    def update_controls(self):
        self.mini_button.setEnabled(self.vault is not None and not self.busy)
        self.mini_panel.search.setEnabled(self.vault is not None and not self.busy)
        self.recent_vaults.setEnabled(not self.busy and self.vault is None)
        for button in [self.open_button, self.create_button, self.unlock_button]:
            button.setEnabled(not self.busy and self.vault is None)
        self.lock_button.setEnabled(self.vault is not None or self.busy)
        self.vault_tab.setEnabled(self.vault is not None and not self.busy)
        self.system_tab.backup.setEnabled(self.vault is not None and not self.busy)
        self.system_tab.import_data.setEnabled(self.vault is not None and not self.busy)
        self.system_tab.export_data.setEnabled(self.vault is not None and not self.busy)
        self.system_tab.open_backup.setEnabled(self.vault is None and not self.busy)
        self.system_tab.autostart.setEnabled(not self.busy and self.autostart.path is not None)

    def show_at_startup(self):
        if self.settings.data["start_minimized"] and self.tray.isSystemTrayAvailable():
            self.in_tray = True
            self.hide()
        else:
            self.in_tray = False
            self.show()

    def change_autostart(self, enabled):
        if self.busy:
            return
        self.startup_pending = True
        self.run_job(lambda: self.autostart.set_enabled(enabled),
                     lambda result: "Автозагрузка включена" if result else "Автозагрузка отключена")

    def change_start_minimized(self, enabled):
        self.settings.data["start_minimized"] = enabled
        self.settings.save()

    def run_job(self, function, callback):
        if self.busy:
            return
        self.busy = True
        self.job_epoch = self.epoch
        self.callback = callback
        self.job = Job(function)
        self.job.signals.done.connect(self.job_done, Qt.ConnectionType.QueuedConnection)
        self.status.setText("Выполняется операция с зашифрованным файлом…")
        self.update_controls()
        self.pool.start(self.job)

    @Slot(object, str)
    def job_done(self, result, error):
        callback = self.callback
        valid = self.job_epoch == self.epoch
        self.callback = self.job = None
        self.busy = False
        if self.startup_pending:
            self.startup_pending = False
            self.settings.data["autostart_enabled"] = self.autostart.enabled()
            self.settings.save()
            self.system_tab.autostart.blockSignals(True)
            self.system_tab.autostart.setChecked(self.settings.data["autostart_enabled"])
            self.system_tab.autostart.blockSignals(False)
        if self.pending_vault:
            self.pending_vault.close()
            self.pending_vault = None
        if not valid:
            if isinstance(result, tuple) and isinstance(result[0], Vault):
                result[0].close()
            self.status.setText("Хранилище заблокировано")
        elif error:
            self.status.setText(error)
            QMessageBox.warning(self, "Операция не выполнена", error)
        else:
            message = callback(result)
            self.status.setText(message or ("Сохранено" if self.vault else "Готово"))
        self.update_controls()
        if self.closing:
            self.close()

    def open_vault(self, create=False, backup=False):
        if self.busy or self.vault:
            return
        suggestion = str(default_vault_path())
        if backup and self.path:
            suggestion = str(self.path) + ".bak"
        if create:
            path, _ = QFileDialog.getSaveFileName(self, "Новый файл хранилища", suggestion, "KeePass (*.kdbx)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Открыть хранилище", suggestion, "KeePass (*.kdbx *.bak)")
        if path:
            self.request_password(Path(path), create)

    def unlock(self):
        if self.path:
            self.request_password(self.path)
        else:
            self.open_vault()

    def refresh_recent(self):
        self.recent_vaults.clear()
        for value in self.settings.data["recent_vaults"]:
            path = Path(value)
            available = path.is_file()
            item = QListWidgetItem(f"{path.name}\n{path.parent}" + (" · файл недоступен" if not available else ""))
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setToolTip(value)
            if not available:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.recent_vaults.addItem(item)
        if not self.recent_vaults.count():
            item = QListWidgetItem("Открытые хранилища появятся здесь.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_vaults.addItem(item)

    def open_recent(self, item):
        if self.vault or self.busy:
            return
        value = item.data(Qt.ItemDataRole.UserRole)
        if not value:
            return
        path = Path(value)
        if not path.is_file():
            self.refresh_recent()
            self.status.setText("Файл недоступен. Найдите его через «Открыть…».")
            return
        self.request_password(path)

    def request_password(self, path, create=False):
        try:
            if create:
                path = validate_vault_path(path)
            elif path.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
                raise ValueError("Переместите хранилище вне каталога приложения перед открытием.")
        except ValueError as error:
            QMessageBox.warning(self, "Расположение файла", str(error))
            return
        dialog = PasswordDialog(self, create)
        self.dialogs.append(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        password = dialog.password.text() if accepted else None
        dialog.scrub()
        self.dialogs.remove(dialog)
        dialog.deleteLater()
        if password:
            operation = Vault.create if create else Vault.open
            self.run_job(lambda: operation(path, password), self.opened)

    def opened(self, result):
        self.vault, self.snapshot = result
        self.path = self.vault.path
        self.settings.remember_vault(self.path)
        self.refresh_recent()
        self.stack.setCurrentIndex(1)
        self.view_mode.sync()
        self.refresh_services()
        self.update_controls()

    def lock(self):
        self.epoch += 1
        for dialog in list(self.dialogs):
            if hasattr(dialog, "scrub"):
                dialog.scrub()
            for edit in dialog.findChildren(QLineEdit):
                edit.clear()
            dialog.reject()
        self.clear_cards()
        self.snapshot = Snapshot()
        self.vault_tab.services.clear()
        self.vault_tab.search.clear()
        self.mini_panel.search.clear()
        self.clipboard.clear_owned()
        if self.vault:
            if self.busy:
                self.pending_vault = self.vault
            else:
                self.vault.close()
            self.vault = None
        self.stack.setCurrentIndex(0)
        self.lock_heading.setText("Хранилище заблокировано")
        self.unlock_button.setText("Разблокировать" if self.path else "Открыть хранилище")
        self.status.setText("Хранилище заблокировано")
        self.update_controls()
        self.view_mode.sync()

    def current_service(self):
        item = self.vault_tab.services.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh_services(self):
        old = self.current_service()
        widget = self.vault_tab.services
        widget.blockSignals(True)
        widget.clear()
        selected = None
        for s in self.snapshot.services:
            count = sum(a.service_id == s.id for a in self.snapshot.accounts)
            item = QListWidgetItem(f"{count}  ·  {s.name}")
            item.setToolTip(s.name)
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            widget.addItem(item)
            if s.id == old:
                selected = item
        if selected:
            widget.setCurrentItem(selected)
        elif widget.count():
            widget.setCurrentRow(0)
        widget.blockSignals(False)
        self.restore_type_filters()
        self.refresh_cards()

    def clear_cards(self):
        for card in self.cards:
            card.scrub()
        self.cards = []
        for layout in (self.vault_tab.cards_layout, self.mini_panel.cards_layout):
            while layout.count() > 1:
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.hide()
                    widget.deleteLater()

    def select_service(self, *args):
        self.restore_type_filters()
        # Смена сервиса и сброс поиска составляют одно обновление карточек.
        search = self.vault_tab.search
        blocked = search.blockSignals(True)
        try:
            search.clear()
        finally:
            search.blockSignals(blocked)
        self.refresh_cards()

    def click_service(self, *args):
        # currentItemChanged уже обработал новый сервис. Повторный клик нужен
        # только для выхода из глобального поиска в текущий сервис.
        if self.vault_tab.search.text():
            self.select_service()

    def type_filter_buttons(self):
        tab = self.vault_tab
        return [("api", tab.filter_api), ("account", tab.filter_account), ("other", tab.filter_other)]

    def restore_type_filters(self):
        service = self.current_service()
        kinds = self.settings.service_filters(self.path, service) if self.vault and service else []
        for kind, button in self.type_filter_buttons():
            blocked = button.blockSignals(True)
            try:
                button.setChecked(kind in kinds)
            finally:
                button.blockSignals(blocked)

    def change_type_filters(self, *args):
        service = self.current_service()
        if self.vault and service:
            kinds = [kind for kind, button in self.type_filter_buttons() if button.isChecked()]
            self.settings.remember_service_filters(self.path, service, kinds)
        self.refresh_cards()

    def refresh_cards(self, *args):
        self.clear_cards()
        if not self.vault:
            return
        tab = self.vault_tab
        mini = self.view_mode.mini
        panel = self.mini_panel if mini else tab
        service_id = self.current_service()
        query = panel.search.text()
        global_search = bool(query.strip())
        if mini:
            accounts = search(self.snapshot, query) if global_search else []
        else:
            accounts = search(self.snapshot, query, None if global_search else service_id,
                              tab.favorites.isChecked()) if service_id or global_search else []
        selected_types = set() if mini else {
            kind for kind, button in self.type_filter_buttons() if button.isChecked()}
        if selected_types:
            accounts = [a for a in accounts if ("account" if a.kind == "legacy" else a.kind) in selected_types]
        name = next((s.name for s in self.snapshot.services if s.id == service_id), "Сервисы")
        tab.heading.setText(("Результаты во всех сервисах" if global_search else name) + f" · {len(accounts)}")
        if mini:
            panel.scroll.setVisible(global_search)
        if not accounts and (not mini or global_search):
            message = "Нет записей для выбранных фильтров. Измените фильтры или поиск." if selected_types else ("Избранных записей нет. Отметьте нужную запись звездой или выключите фильтр." if tab.favorites.isChecked() else ("Ничего не найдено. Измените запрос." if query else "Добавьте сервис слева, затем запись кнопкой «+»."))
            panel.cards_layout.insertWidget(0, label(message, "muted", True))
        for a in accounts:
            callbacks = (a, self.copy_value, self.edit_account, self.delete_account,
                         self.toggle_favorite)
            card = AccountCard(*callbacks, compact=True) if mini else AccountCard(*callbacks)
            # Таймер масштабирования срабатывает после первого Show:
            # подготовим геометрию до добавления карточки в видимую панель.
            card.ensurePolished()
            metrics(card, self.ui_scale.state.scale_factor)
            self.cards.append(card)
            panel.cards_layout.insertWidget(panel.cards_layout.count() - 1, card)
            if mini:
                card.expand.toggled.connect(self.view_mode.schedule_fit)
        tab.add_record.setEnabled(bool(self.snapshot.services) and not self.busy)
        self.view_mode.schedule_fit()

    def toggle_favorite(self, account):
        if self.vault and not self.busy:
            changed = copy.deepcopy(account)
            changed.favorite = not changed.favorite
            vault = self.vault
            self.run_job(lambda: vault.account(changed), self.saved)

    def copy_value(self, value):
        if self.vault and not self.busy:
            self.clipboard.copy(value)
            self.status.setText("Скопировано.")
            return True
        return False

    def hide_secrets(self):
        for card in self.cards:
            card.hide_secrets()

    def focus_search(self):
        if self.vault:
            if self.view_mode.mini:
                self.mini_panel.search.setFocus()
            else:
                self.tabs.setCurrentIndex(0)
                self.vault_tab.search.setFocus()

    def saved(self, result):
        self.snapshot = result
        self.refresh_services()

    def edit_service(self, existing=False):
        if not self.vault or self.busy:
            return
        id = self.current_service() if existing else None
        if existing and not id:
            return
        name = next((s.name for s in self.snapshot.services if s.id == id), "")
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Изменить сервис" if existing else "Новый сервис")
        dialog.setLabelText("Название сервиса")
        dialog.setTextValue(name)
        dialog.setOkButtonText("Сохранить")
        dialog.setCancelButtonText("Отмена")
        self.dialogs.append(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        name = dialog.textValue().strip()
        dialog.setTextValue("")
        self.dialogs.remove(dialog)
        dialog.deleteLater()
        if accepted and self.vault:
            vault = self.vault
            self.run_job(lambda: vault.service(name, id), self.saved)

    def confirm(self, text, title="Подтвердите удаление"):
        dialog = QMessageBox(QMessageBox.Icon.Warning, title, text,
                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        self.dialogs.append(dialog)
        answer = dialog.exec() == QMessageBox.StandardButton.Yes
        dialog.setText("")
        self.dialogs.remove(dialog)
        dialog.deleteLater()
        return answer and self.vault is not None

    def delete_service(self):
        if not self.vault or self.busy:
            return
        id = self.current_service()
        if id and self.confirm("Удалить сервис со всеми его аккаунтами? Предыдущая версия останется в резервной копии."):
            vault = self.vault
            self.run_job(lambda: vault.service("", id, delete=True), self.saved)

    def edit_account(self, account=None, kind="account"):
        if not self.vault or self.busy or not self.snapshot.services:
            return
        self.hide_secrets()
        if account and account.kind not in ("api", "account", "other"):
            dialog = AccountDialog(self, self.snapshot.services, account, self.current_service())
        else:
            dialog = RecordDialog(self, self.snapshot.services, account, self.current_service(), kind)
        self.dialogs.append(dialog)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        result = dialog.result_account if accepted else None
        dialog.scrub()
        self.dialogs.remove(dialog)
        dialog.deleteLater()
        if result and self.vault:
            vault = self.vault
            self.run_job(lambda: vault.account(result), self.saved)

    def delete_account(self, account):
        if self.vault and not self.busy and self.confirm("Удалить запись? Предыдущая версия останется в резервной копии."):
            vault = self.vault
            self.run_job(lambda: vault.account(account, delete=True), self.saved)

    def export_backup(self):
        if not self.vault or self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить зашифрованную копию", str(self.path.parent / "Копия.kdbx"), "KeePass (*.kdbx)")
        if path:
            try:
                path = validate_vault_path(path)
            except ValueError as error:
                QMessageBox.warning(self, "Расположение файла", str(error))
                return
            vault = self.vault
            self.run_job(lambda: vault.export_backup(path), lambda result: None)

    def import_data(self):
        if not self.vault or self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Импортировать записи", "", "Файл обмена (*.json)")
        if not path or not self.vault:
            return
        try:
            incoming = read_exchange(path)
        except ExchangeError as error:
            QMessageBox.warning(self, "Импорт", str(error))
            return
        count = len(incoming.accounts)
        if not self.confirm(f"Импортировать {len(incoming.services)} сервисов и {count} записей? Существующие данные сохранятся, точные повторы будут пропущены.", "Импорт записей"):
            return
        vault = self.vault
        self.run_job(lambda: vault.import_records(incoming), self.imported)

    def imported(self, result):
        state, counts = result
        self.saved(state)
        return f"Импорт завершён: добавлено {counts['added']}, пропущено повторов {counts['skipped']}, новых сервисов {counts['services']}."

    def export_data(self):
        if not self.vault or self.busy:
            return
        scope, accepted = QInputDialog.getItem(self, "Экспорт записей", "Какие сервисы экспортировать?", ["Все сервисы", "Текущий сервис"], 0, False)
        if not accepted or not self.vault:
            return
        state = copy.deepcopy(self.snapshot)
        if scope == "Текущий сервис":
            service_id = self.current_service()
            state.services = [s for s in state.services if s.id == service_id]
            state.accounts = [a for a in state.accounts if a.service_id == service_id]
        path, _ = QFileDialog.getSaveFileName(self, "Экспортировать открытый JSON", "Экспорт Acc-storage.json", "Файл обмена (*.json)")
        if path and self.vault:
            self.run_job(lambda: write_exchange(path, state), lambda result: "Файл обмена сохранён. Он содержит открытые ключи и пароли.")

    def restore_geometry(self):
        d = self.settings.data
        rect = QRect(d["window_pos_x"], d["window_pos_y"], d["window_width"], d["window_height"])
        screens = QApplication.screens()
        screen = next((s for s in screens if s.availableGeometry().contains(rect)), screens[0])
        available = screen.availableGeometry()
        rect.setWidth(min(rect.width(), available.width()))
        rect.setHeight(min(rect.height(), available.height()))
        if not available.contains(rect):
            rect.moveCenter(available.center())
        self.setGeometry(rect)
        self.vault_tab.splitter.setSizes(d["splitter"])
        if d["maximized"]:
            self.setWindowState(Qt.WindowState.WindowMaximized)

    def save_geometry(self):
        if not self.isVisible() or self.isMinimized():
            return
        if hasattr(self, "view_mode"):
            if self.view_mode.switching:
                return
            if self.view_mode.mini:
                self.view_mode.save_geometry()
                return
        rect = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings.data.update(window_pos_x=rect.x(), window_pos_y=rect.y(),
                                  window_width=rect.width(), window_height=rect.height(),
                                  maximized=self.isMaximized(), splitter=self.vault_tab.splitter.sizes())
        self.settings.save()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "geometry_timer"):
            self.geometry_timer.start(400)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "view_mode"):
            self.view_mode.resized()
        if hasattr(self, "geometry_timer"):
            self.geometry_timer.start(400)

    def closeEvent(self, event):
        self.save_geometry()
        if not self.exiting and self.tray.isSystemTrayAvailable():
            event.ignore()
            self.in_tray = True
            self.hide()
            return
        self.lock()
        if self.busy:
            self.closing = True
            event.ignore()
            return
        self.ui_scale.stop()
        self.view_mode.stop()
        self.tray.hide()
        self.geometry_timer.stop()
        event.accept()
        QApplication.instance().quit()

    def exit_application(self):
        self.exiting = True
        self.close()
