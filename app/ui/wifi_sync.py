import base64
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime

import qrcode
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from app.core.settings import ROOT
from app.services.manual_sync import ManualOutbox
from app.services.sync_review import SyncReview
from app.services.vault import VaultError, fingerprint
from app.services.wifi_sync import (
    SyncIdentity,
    SyncServer,
    local_addresses,
    preferred_address,
)
from app.ui.widgets import Button, label


@dataclass
class Request:
    path: str
    body: dict
    ready: threading.Event = field(default_factory=threading.Event)
    response: tuple = (503, {})


class WifiSync(QObject):
    incoming = Signal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.server = None
        self.identity = None
        self.pending = []
        self.review = None
        self.outbox = None
        self.review_dialog = None
        self.review_button = Button("Ожидающие изменения телефона…", self.show_review)
        self.review_button.hide()
        self.incoming.connect(self.handle, Qt.ConnectionType.QueuedConnection)
        self.connect_button = Button("Связать телефон по Wi-Fi…", self.pair)
        self.stop_button = Button("Остановить обмен", lambda: self.stop(disable=True))
        self.revoke_button = Button("Отозвать доступ телефонов", self.revoke)
        self.message = label("Обмен выключен. Откройте хранилище и свяжите телефон.", "muted", True)
        layout = window.system_tab.scroll.widget().layout()
        position = layout.count() - 1
        layout.insertWidget(position, label("Мобильный KeyShelf", "sectionTitle"))
        row = QHBoxLayout()
        row.addWidget(self.connect_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.revoke_button)
        layout.insertLayout(position + 1, row)
        layout.insertWidget(position + 2, self.message)
        layout.insertWidget(position + 3, self.review_button)

    def ensure_outbox(self):
        vault = self.window.vault
        if vault and (self.outbox is None or self.outbox.vault is not vault):
            self.outbox = ManualOutbox(
                self.window.settings.path.parent / ".local-state" / "wifi-sync" / "manual", vault
            )
        return self.outbox if vault else None

    def publish(self):
        outbox = self.ensure_outbox()
        if not outbox or self.window.busy:
            return
        if outbox.publish():
            self.message.setText("Пакет сохранён · ожидается доставка и ответ телефона")
            if self.server:
                self.server.notify()
        self.window.update_controls()

    def dispatch(self, path, body):
        request = Request(path, body)
        self.incoming.emit(request)
        if not request.ready.wait(18):
            request.ready.set()
            return 503, {}
        return request.response

    def handle(self, request):
        window = self.window
        if not self.server or not window.vault or window.busy or request.ready.is_set():
            request.ready.set()
            return
        vault = window.vault
        try:
            if request.body.get("protocol") != 3:
                request.response = (
                    426,
                    {"error": "Обновите обе версии KeyShelf для подтверждаемого обмена"},
                )
                request.ready.set()
                return
            if fingerprint(vault.path) != vault.digest:
                request.response = 409, {}
                request.ready.set()
                return
            if self.review is None or self.review.vault is not vault:
                self.review = SyncReview(
                    window.settings.path.parent / ".local-state" / "wifi-sync" / "reviews-v3", vault
                )
            if self.outbox is None or self.outbox.vault is not vault:
                self.outbox = ManualOutbox(
                    self.window.settings.path.parent / ".local-state" / "wifi-sync" / "manual",
                    vault,
                )
            if request.path == "/sync":
                response = {"action": "idle", "hash": vault.digest.hex(), "name": vault.path.name}
                response["protocol"] = 3
                response["modified"] = int(vault.path.stat().st_mtime * 1000)
                state = self.review.state
                if (
                    self.review.active
                    and state.get("remote") == request.body.get("outgoing")
                    and state.get("decision") == "accept_phone"
                ):
                    self.pending.append(request)

                    def completed(result):
                        window.snapshot = result
                        window.refresh_services()
                        request.response = (
                            200,
                            {
                                "protocol": 3,
                                "action": "ack",
                                "hash": vault.digest.hex(),
                                "modified": int(vault.path.stat().st_mtime * 1000),
                            },
                        )
                        request.ready.set()
                        if request in self.pending:
                            self.pending.remove(request)
                        self.outbox.received(vault.digest.hex())
                        self.review.state = {}
                        self.review.save()
                        window.update_controls()
                        self.review_button.hide()
                        self.message.setText("Изменения телефона приняты · базы одинаковые")
                        return "Синхронизировано с телефоном"

                    window.run_job(self.review.apply, completed)
                    return
                if (
                    self.review.active
                    and state.get("remote") == request.body.get("outgoing")
                    and state.get("decision") == "restore_phone"
                ):
                    response["action"] = "restore"
                    response["expectedLocal"] = state["remote"]
                    if request.body.get("hash") != state["remote"]:
                        request.response = 409, {}
                        request.ready.set()
                        return
                    response["blob"] = base64.b64encode(vault.path.read_bytes()).decode()
                if (
                    state.get("decision") == "restore_phone"
                    and request.body.get("hash") == vault.digest.hex()
                ):
                    self.review.state = {}
                    self.review.save()
                outgoing = self.outbox.state.get("outgoing")
                if outgoing and (
                    request.body.get("base") == outgoing or request.body.get("hash") == outgoing
                ):
                    self.outbox.acknowledge(outgoing)
                    window.update_controls()
                    outgoing = None
                if response["action"] != "restore":
                    if outgoing:
                        response.update(
                            action="pull",
                            hash=outgoing,
                            modified=self.outbox.state["modified"],
                            blob=base64.b64encode(self.outbox.payload()).decode(),
                        )
                    elif request.body.get("outgoing"):
                        response["action"] = "push"
                if response["action"] == "idle":
                    self.message.setText("Ручная отправка · нажмите «Сохранить» после изменений")
                else:
                    self.message.setText("Сохранённый пакет ожидает ответа")
                request.response = 200, response
                request.ready.set()
                return
            if request.path != "/upload":
                raise ValueError
            expected = request.body["expected"]
            if not isinstance(expected, str) or len(expected) != 64:
                raise ValueError
            if fingerprint(vault.path).hex() != expected:
                request.response = 409, {}
                request.ready.set()
                return
            raw = base64.b64decode(request.body["blob"], validate=True)
            old_key = self.review.state.get("key")
            self.review.offer(raw, expected, request.body.get("modified", 0))
            if self.review_dialog and old_key != self.review.state["key"]:
                self.review_dialog.reject()
            if request.body.get("decision") == "restore_desktop":
                self.pending.append(request)

                def completed(result):
                    window.snapshot = result
                    window.refresh_services()
                    request.response = (
                        200,
                        {"protocol": 3, "action": "same", "hash": vault.digest.hex()},
                    )
                    request.ready.set()
                    if request in self.pending:
                        self.pending.remove(request)
                    if self.review_dialog:
                        self.review_dialog.reject()
                    self.outbox.received(vault.digest.hex())
                    window.update_controls()
                    self.review_button.hide()
                    self.message.setText(
                        "Телефон отклонил изменения · база компьютера восстановлена"
                    )
                    return "База восстановлена по ответу телефона"

                window.run_job(self.review.apply, completed)
                return
            if request.body.get("decision") not in (None, "offer"):
                raise ValueError
            request.response = (
                200,
                {"protocol": 3, "action": "pending", "hash": self.review.state["remote"]},
            )
            request.ready.set()
            self.review_button.show()
            self.message.setText("Изменения телефона ожидают подтверждения")
            if not self.review.state["decision"] and not self.review_dialog:
                self.show_review()
        except (ValueError, KeyError, TypeError, OSError, VaultError):
            request.response = 400, {}
            request.ready.set()

    def show_review(self):
        review = self.review
        if self.review_dialog or not review or not review.active or self.window.busy:
            return
        box = QMessageBox(self.window)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowTitle("Принять изменения с телефона?")
        timestamp = review.state.get("modified", 0)
        date = (
            datetime.fromtimestamp(timestamp / 1000).strftime("%d.%m.%Y %H:%M:%S")
            if timestamp
            else "дата неизвестна"
        )
        box.setText(f"База телефона изменена: {date}.\nПринять изменения?")
        accept = box.addButton("Принять", QMessageBox.ButtonRole.AcceptRole)
        reject = box.addButton("Отклонить", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(accept)
        self.review_dialog = box
        key = review.state["key"]

        def finished(_):
            self.review_dialog = None
            if (
                self.review is not review
                or self.window.vault is not review.vault
                or review.state.get("key") != key
                or not review.active
            ):
                box.deleteLater()
                return
            clicked = box.clickedButton()
            if clicked == accept and not self.window.busy:
                review.accept_phone()
                self.review_button.hide()
                self.message.setText("Изменения приняты · применение при следующем обмене")
            elif clicked == reject:
                review.reject_phone()
                self.review_button.hide()
                self.message.setText(
                    "Изменения отклонены · телефон восстановится при следующем обмене"
                )
            if clicked in (accept, reject) and self.server:
                self.server.notify()
            box.deleteLater()

        box.finished.connect(finished)
        box.open()

    def pair(self):
        if not self.window.vault or self.window.busy:
            QMessageBox.information(self.window, "Wi-Fi", "Сначала откройте хранилище.")
            return
        addresses = local_addresses()
        if not addresses:
            QMessageBox.information(
                self.window,
                "Wi-Fi",
                "Локальный IPv4 не найден. Подключите компьютер к домашней сети.",
            )
            return
        try:
            if self.identity is None:
                self.identity = SyncIdentity(ROOT / ".local-state" / "wifi-sync")
            dialog = QDialog(self.window)
            dialog.setWindowTitle("Связать мобильный KeyShelf")
            layout = QVBoxLayout(dialog)
            layout.addWidget(
                label(
                    "Телефон и компьютер должны быть в одной домашней сети.\nРазрешите KeyShelf доступ к частной сети, если Windows спросит.",
                    "muted",
                    True,
                )
            )
            combo = QComboBox()
            combo.addItems(addresses)
            combo.setCurrentText(preferred_address(addresses, self.identity.data.get("host")))
            layout.addWidget(combo)
            image_label = QLabel()
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image_label)
            layout.addWidget(
                label(
                    "В телефоне: ⋮ → Настройки → Синхронизация → Сканировать QR.\nПриглашение действует 2 минуты и используется один раз.",
                    "muted",
                    True,
                )
            )

            def invitation():
                self.stop()
                host = combo.currentText()
                path = str(self.window.vault.path.resolve())
                if self.identity.data.get("vault") != path:
                    self.identity.data["tokens"] = []
                self.server = SyncServer(self.identity, self.dispatch, host)
                self.identity.data.update(host=host, vault=path, enabled=True)
                self.identity.save()
                payload = json.dumps(
                    self.identity.invitation(host, self.server.port), separators=(",", ":")
                )
                matrix = qrcode.QRCode(border=4)
                matrix.add_data(payload)
                matrix.make(fit=True)
                cells = matrix.get_matrix()
                scale = max(1, 360 // len(cells))
                image = QImage(len(cells) * scale, len(cells) * scale, QImage.Format.Format_RGB32)
                image.fill(QColor("white"))
                for y, line in enumerate(cells):
                    for x, black in enumerate(line):
                        if black:
                            for dy in range(scale):
                                for dx in range(scale):
                                    image.setPixelColor(
                                        x * scale + dx, y * scale + dy, QColor("black")
                                    )
                image_label.setPixmap(QPixmap.fromImage(image))
                self.message.setText(
                    f"Обмен включён: {host}:{self.server.port} · только локальная сеть"
                )

            combo.currentTextChanged.connect(invitation)
            layout.addWidget(Button("Обновить QR", invitation))
            invitation()
            dialog.exec()
        except Exception:
            self.stop()
            QMessageBox.warning(
                self.window,
                "Wi-Fi",
                "Не удалось включить обмен. Проверьте локальную сеть и доступность порта 48732.",
            )

    def stop(self, disable=False):
        if self.review_dialog:
            self.review_dialog.reject()
        self.review = None
        self.review_button.hide()
        for request in self.pending:
            request.ready.set()
        self.pending.clear()
        if self.server:
            self.server.close()
            self.server = None
        self.message.setText("Обмен выключен. Нажмите «Связать телефон» для включения.")
        if disable and self.identity:
            self.identity.data["enabled"] = False
            self.identity.save()

    def resume(self):
        if not (ROOT / ".local-state" / "wifi-sync" / "pairing.dpapi").exists():
            return
        try:
            if self.identity is None:
                self.identity = SyncIdentity(ROOT / ".local-state" / "wifi-sync")
            data = self.identity.data
            if data.get("enabled") and data.get("vault") == str(self.window.vault.path.resolve()):
                if data.get("host") not in local_addresses():
                    self.message.setText("Адрес сети изменился. Свяжите телефон заново.")
                    return
                self.server = SyncServer(self.identity, self.dispatch, data["host"])
                self.ensure_outbox()
                self.review = SyncReview(
                    self.window.settings.path.parent / ".local-state" / "wifi-sync" / "reviews-v3",
                    self.window.vault,
                )
                if self.outbox.state.get("outgoing") or self.review.state.get("decision"):
                    self.server.notify()
                self.message.setText(f"Обмен по Wi-Fi включён: {data['host']}:48732")
        except Exception:
            self.message.setText(
                "Адрес компьютера изменился или порт занят. Свяжите телефон заново."
            )

    def job_failed(self):
        for request in self.pending:
            request.ready.set()
        self.pending.clear()

    def revoke(self):
        if (
            self.identity is None
            and (ROOT / ".local-state" / "wifi-sync" / "pairing.dpapi").exists()
        ):
            self.identity = SyncIdentity(ROOT / ".local-state" / "wifi-sync")
        if self.identity:
            self.identity.revoke()
        self.stop(disable=True)
        self.message.setText("Доступ телефонов отозван. Для подключения нужен новый QR.")
