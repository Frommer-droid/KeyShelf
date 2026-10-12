"""Non-interactive validation of the actual frozen executable, with synthetic data."""
import io
import json
import sys
import tempfile
from pathlib import Path


def check(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        from PySide6.QtGui import QPixmap

        from app.core.application import create_application
        from app.core.models import Account, Field
        from app.core.resources import resource_path
        from app.core.settings import ROOT, Settings
        from app.services.autostart import Autostart
        from app.services.exchange import document, parse
        from app.services.sync_review import SyncReview
        from app.services.totp import current_code
        from app.services.vault import Vault
        from app.ui.main_window import MainWindow
        from app.ui.record_dialog import RecordDialog
        from app.ui.widgets import CopyIconButton

        application = create_application([])
        assert not application.windowIcon().pixmap(32, 32).isNull()
        assert not QPixmap(str(resource_path("assets/ui/chevron-down.svg"))).isNull()
        assert resource_path("VERSION").read_text().strip() == (ROOT / "VERSION").read_text().strip()
        assert not report["frozen"] or ROOT == Path(sys.executable).parent
        with tempfile.TemporaryDirectory(prefix="acc-storage-frozen-smoke-", dir=Path(report_path).parent) as directory:
            folder = Path(directory)
            vault, _ = Vault.create(folder / "synthetic.kdbx", "synthetic-runtime-test-123")
            try:
                state = vault.service("Synthetic")
                state = vault.account(Account(service_id=state.services[0].id, title="Synthetic API", kind="api",
                                              fields=[Field("API-ключ", "synthetic-value")]))
                assert document(parse(document(state))) == document(state)
                vault.close()
                vault, state = Vault.open(folder / "synthetic.kdbx", "synthetic-runtime-test-123")
                assert state.accounts[0].fields[0].value == "synthetic-value"
                assert len(current_code("JBSWY3DPEHPK3PXP")[0]) == 6
                window = MainWindow(Settings(folder / "settings.json"), Autostart(folder / "Startup"))
                window.opened((vault, state))
                assert window.cards and not window.isVisible()
                window.system_tab.scale_combo.setCurrentIndex(window.system_tab.scale_combo.findData(20))
                assert window.ui_scale.state.delta_percent == 20
                window.view_mode.set_mini(True)
                assert window.view_mode.mini and not window.cards
                window.mini_panel.search.setText("Synthetic")
                application.processEvents()
                assert len(window.cards) == 1 and not window.isVisible()
                mini_card = window.cards[0]
                mini_card.expand.click()
                assert mini_card.expand.isChecked() and not mini_card.body.isHidden()
                assert mini_card.findChildren(CopyIconButton)
                window.view_mode.set_mini(False)
                assert not window.view_mode.mini and not window.isVisible()
                editor = RecordDialog(window, state.services, account=state.accounts[0])
                assert editor.record_type.isEnabled()
                editor.favorite.click()
                assert editor.favorite.isChecked()
                editor.add_field.click()
                editor.extra_inputs[0].setText("synthetic-extra")
                editor.record_type.setCurrentIndex(editor.record_type.findData("other"))
                editor.submit()
                changed = editor.result_account
                assert changed.kind == "other"
                assert changed.favorite
                assert [field.value for field in changed.fields] == ["synthetic-value", "synthetic-extra", ""]
                updated = vault.account(changed)
                assert document(parse(document(updated))) == document(updated)
                editor.scrub()
                editor.deleteLater()
                updated = vault.service("Synthetic destination")
                destination = next(s for s in updated.services if s.name == "Synthetic destination")
                move_editor = RecordDialog(window, updated.services, account=updated.accounts[0])
                move_editor.service.setCurrentIndex(move_editor.service.findData(destination.id))
                move_editor.submit()
                moved = vault.account(move_editor.result_account)
                assert moved.accounts[0].service_id == destination.id
                assert moved.accounts[0].fields == updated.accounts[0].fields
                move_editor.scrub()
                move_editor.deleteLater()
                # Exercise the actual frozen review module with synthetic deletion.
                before_sync = vault.path.read_bytes()
                outbox = window.wifi_sync.ensure_outbox()
                assert outbox.dirty and outbox.publish()
                assert outbox.payload() == before_sync
                assert str(vault.path) in window.database_label.text()
                kp = Vault.decode(before_sync, vault.password)
                kp.delete_entry(kp.entries[0])
                buffer = io.BytesIO()
                kp.save(buffer)
                incoming = buffer.getvalue()
                review = SyncReview(folder / "sync-copies", vault)
                review.offer(incoming, vault.digest.hex(), modified=1791790000000)
                assert vault.path.read_bytes() == before_sync
                review.reject_phone()
                assert review.state["decision"] == "restore_phone"
                assert vault.path.read_bytes() == before_sync
                result = review.apply()
                assert not result.accounts and vault.path.read_bytes() == incoming
                assert outbox.payload() == before_sync
                assert vault.path.with_suffix(".kdbx.bak").read_bytes() == before_sync
                window.exit_application()
            finally:
                vault.close()
        report.update(ok=True, checks=["QtCore/Gui/Widgets", "icon", "resources", "KDBX create/read/write",
                                      "Argon2/AES", "JSON", "TOTP", "UI scale", "extra fields/type change",
                                      "mini search/accordion/copy controls", "mode roundtrip",
                                      "manual Save/immutable batch/database identity", "confirmed sync/mirror deletion/rejection/backup", "record service move", "record favorite draft", "dropdown chevron", "hidden window", "clean close"])
    except Exception as error:
        report["error_type"] = type(error).__name__
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
