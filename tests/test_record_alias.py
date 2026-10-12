import copy

import pytest

from app.core.models import Account, Service, Snapshot, search
from app.services.exchange import ExchangeError, document, identity, parse
from app.services.vault import Vault
from app.ui.cards import AccountCard
from app.ui.record_dialog import RecordDialog


@pytest.mark.parametrize("kind", ["account", "api", "other"])
def test_name_and_alias_survive_editor_search_and_kdbx(qtapp, tmp_path, kind):
    path = tmp_path / "alias.kdbx"
    vault, _ = Vault.create(path, "synthetic-master-123")
    service = vault.service("Google").services[0]
    dialog = RecordDialog(None, [service], kind=kind)
    try:
        dialog.inputs["title"].setText("Личный аккаунт")
        dialog.all_inputs["alias"].setText(" .p ")
        assert dialog.all_inputs["title"].placeholderText() == "Название"
        assert dialog.form.getWidgetPosition(dialog.field_rows["title"])[0] < dialog.form.getWidgetPosition(dialog.field_rows["alias"])[0]
        for next_kind in ("other", "api", kind):
            dialog.record_type.setCurrentIndex(dialog.record_type.findData(next_kind))
            assert dialog.all_inputs["alias"].text() == " .p "
        dialog.submit()
        state = vault.account(dialog.result_account)
        assert search(state, ".p")[0].title == "Личный аккаунт"
        card = AccountCard(state.accounts[0], lambda _: None, lambda _: None, lambda _: None, compact=True)
        assert ".p" not in card.expand.text()
        assert "Личный аккаунт" in card.expand.text()
        card.deleteLater()
        vault.close()
        vault, reopened = Vault.open(path, "synthetic-master-123")
        account = reopened.accounts[0]
        assert account.title == "Личный аккаунт" and account.alias == ".p"
        assert search(reopened, "Google .p") == [account]
        restored = RecordDialog(None, [service], account=account)
        assert restored.all_inputs["alias"].text() == ".p"
        restored.scrub()
        assert not restored.all_inputs["alias"].text()
        restored.deleteLater()
    finally:
        dialog.deleteLater()
        vault.close()


def test_optional_alias_and_legacy_exchange():
    state = Snapshot([Service("s", "Google")], [Account(service_id="s", title="Old title", kind="legacy")])
    data = document(state)
    data["services"][0]["records"][0].pop("alias")
    old = parse(data).accounts[0]
    assert old.title == "Old title" and old.alias == ""
    newer = copy.deepcopy(old)
    newer.alias = ".p"
    state.services[0].id = newer.service_id
    state.accounts = [newer]
    assert parse(document(state)).accounts[0].alias == ".p"
    assert identity(old) != identity(newer)
    data["services"][0]["records"][0]["alias"] = 12
    with pytest.raises(ExchangeError):
        parse(data)


def test_title_required_but_alias_optional(qtapp):
    dialog = RecordDialog(None, [Service("s", "Google")])
    try:
        dialog.all_inputs["alias"].setText(".p")
        dialog.submit()
        assert dialog.result_account is None
        assert "название" in dialog.error.text()
        dialog.inputs["title"].setText("Personal")
        dialog.all_inputs["alias"].clear()
        dialog.submit()
        assert dialog.result_account.title == "Personal"
        assert dialog.result_account.alias == ""
    finally:
        dialog.deleteLater()


def test_root_service_caption_does_not_rename_kdbx(tmp_path):
    path = tmp_path / "root-caption.kdbx"
    vault, _ = Vault.create(path, "synthetic-master-123")
    try:
        db = vault.decode(path.read_bytes(), vault.password)
        root_id = str(db.root_group.uuid)
        db.root_group.name = "Root"
        # Work only with this synthetic fixture, never rewrite owner vaults.
        db.save(str(path))
        vault.close()
        vault, _ = Vault.open(path, "synthetic-master-123")
        state = vault.account(Account(service_id=root_id, title="Synthetic", kind="other"))
        assert state.services[0].name == "Без сервиса"
        assert state.accounts[0].service == "Без сервиса"
        db = vault.decode(path.read_bytes(), vault.password)
        assert db.root_group.name == "Root"
    finally:
        vault.close()
