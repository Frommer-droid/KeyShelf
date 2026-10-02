"""Non-interactive validation of the actual frozen executable, with synthetic data."""
import json
import sys
import tempfile
from pathlib import Path


def check(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        from app.core.application import create_application
        from app.core.models import Account, Field
        from app.core.resources import resource_path
        from app.core.settings import ROOT, Settings
        from app.services.autostart import Autostart
        from app.services.exchange import document, parse
        from app.services.totp import current_code
        from app.services.vault import Vault
        from app.ui.main_window import MainWindow
        from app.ui.record_dialog import RecordDialog
        from app.ui.widgets import CopyIconButton

        application = create_application([])
        assert not application.windowIcon().pixmap(32, 32).isNull()
        assert resource_path("VERSION").read_text().strip() == "0.3.0"
        assert not report["frozen"] or ROOT == Path(sys.executable).parent
        with tempfile.TemporaryDirectory(prefix="acc-storage-frozen-smoke-") as directory:
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
                editor.add_field.click()
                editor.extra_inputs[0].setText("synthetic-extra")
                editor.record_type.setCurrentIndex(editor.record_type.findData("other"))
                editor.submit()
                changed = editor.result_account
                assert changed.kind == "other"
                assert [field.value for field in changed.fields] == ["synthetic-value", "synthetic-extra", ""]
                updated = vault.account(changed)
                assert document(parse(document(updated))) == document(updated)
                editor.scrub()
                editor.deleteLater()
                window.exit_application()
            finally:
                vault.close()
        report.update(ok=True, checks=["QtCore/Gui/Widgets", "icon", "resources", "KDBX create/read/write",
                                      "Argon2/AES", "JSON", "TOTP", "UI scale", "extra fields/type change",
                                      "mini search/accordion/copy controls", "mode roundtrip",
                                      "hidden window", "clean close"])
    except Exception as error:
        report["error_type"] = type(error).__name__
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
