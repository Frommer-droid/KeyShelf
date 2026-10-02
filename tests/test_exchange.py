import copy

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog

from app.core.models import Account, Field, Service, Snapshot
from app.services.exchange import ExchangeError, document, parse, read_exchange, write_exchange
from app.services.vault import Vault, VaultError
from tests.test_ui import make_window, process
from tools.prepare_text_import import convert


def sample():
    return Snapshot([Service("a", "Test"), Service("b", "Empty")], [
        Account(service_id="a", title="API", kind="api", notes="multi\nline", favorite=True, api_paid=True, fields=[Field("API-ключ", "synthetic-key")]),
        Account(service_id="a", title="Account", login="test@example.invalid", kind="account", fields=[Field("Пароль", "synthetic-password"), Field("Секрет 2FA", "")]),
        Account(service_id="a", title="Legacy", kind="legacy", project="keep", fields=[Field("Extra", "extra", False)]),
    ])


def test_exchange_roundtrip_and_no_overwrite(tmp_path):
    path = tmp_path / "exchange.json"
    state = sample()
    write_exchange(path, state)
    assert document(read_exchange(path)) == document(state)
    original = path.read_bytes()
    with pytest.raises(ExchangeError):
        write_exchange(path, Snapshot())
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".exchange-*"))


@pytest.mark.parametrize("change", [
    lambda d: d.update(version=2),
    lambda d: d["services"].append(copy.deepcopy(d["services"][0])),
    lambda d: d["services"][0]["records"][0].update(kind="unknown"),
    lambda d: d["services"][0]["records"][0]["fields"][0].update(secret=False),
])
def test_invalid_schema_rejected(change):
    data = document(sample())
    change(data)
    with pytest.raises(ExchangeError) as error:
        parse(data)
    assert "synthetic" not in str(error.value)


def test_duplicate_json_keys_and_bad_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version":1,"version":2}', encoding="utf-8")
    with pytest.raises(ExchangeError):
        read_exchange(path)
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ExchangeError):
        read_exchange(path)


def test_paid_flag_backward_compatibility():
    data = document(sample())
    assert parse(data).accounts[0].api_paid
    for service in data["services"]:
        for record in service["records"]:
            record.pop("api_paid")
    assert not parse(data).accounts[0].api_paid
    data["services"][0]["records"][0]["api_paid"] = "yes"
    with pytest.raises(ExchangeError):
        parse(data)


def test_atomic_merge_duplicates_and_backup(tmp_path):
    path = tmp_path / "synthetic.kdbx"
    vault, _ = Vault.create(path, "synthetic-passphrase-123")
    try:
        before = path.read_bytes()
        incoming = parse(document(sample()))
        state, counts = vault.import_records(incoming)
        assert counts == {"added": 3, "skipped": 0, "services": 2}
        assert path.with_name(path.name + ".bak").read_bytes() == before
        repeated, counts = vault.import_records(incoming)
        assert repeated == state
        assert counts == {"added": 0, "skipped": 3, "services": 0}
        # A changed favorite does not turn the same credential into a new record.
        incoming.accounts[0].favorite = False
        assert vault.import_records(incoming)[1]["skipped"] == 3
        raw = path.read_bytes()
        assert b"synthetic-key" not in raw
        bad = copy.deepcopy(incoming)
        bad.accounts[0].fields[0].value = None
        with pytest.raises(ExchangeError):
            vault.import_records(bad)
        assert path.read_bytes() == raw
        path.write_bytes(raw + b"external-change")
        with pytest.raises(VaultError):
            vault.import_records(incoming)
    finally:
        vault.close()


def test_import_export_ui(qtapp, tmp_path, monkeypatch):
    window = make_window(qtapp, tmp_path)
    try:
        incoming = tmp_path / "incoming.json"
        outgoing = tmp_path / "outgoing.json"
        write_exchange(incoming, sample())
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(incoming), ""))
        monkeypatch.setattr(window, "confirm", lambda *args: True)
        window.import_data()
        process(qtapp, lambda: not window.busy)
        assert len(window.snapshot.accounts) == 4
        assert "добавлено 3" in window.status.text()
        monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("Все сервисы", True))
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(outgoing), ""))
        window.export_data()
        process(qtapp, lambda: not window.busy)
        assert document(read_exchange(outgoing)) == document(window.snapshot)
        selected = tmp_path / "selected.json"
        monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("Текущий сервис", True))
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(selected), ""))
        service_id = window.current_service()
        window.export_data()
        process(qtapp, lambda: not window.busy)
        exported = read_exchange(selected)
        assert len(exported.services) == 1
        assert len(exported.accounts) == sum(a.service_id == service_id for a in window.snapshot.accounts)
        window.lock()
        assert not window.system_tab.import_data.isEnabled()
        assert not window.system_tab.export_data.isEnabled()
    finally:
        window.exit_application()


def test_reviewed_text_conversion_coverage(tmp_path):
    lines = [""] * 74
    headers = [1, 5, 8, 11, 14, 17, 21, 26, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 55, 57, 60, 63, 66, 69, 72]
    values = [2, 3, 6, 9, 12, 15, 18, 19, 22, 28, 31, 34, 37, 40, 43, 46, 49, 52, 56, 58, 61, 64, 67, 70, 73]
    for i in headers:
        lines[i - 1] = f"label {i}"
    for i in values:
        lines[i - 1] = f"synthetic-{i}"
    path = tmp_path / "synthetic.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = convert(path)
    assert len(state.accounts) == 22
    assert len(state.services) == 12
    assert all(a.title != "label 48" for a in state.accounts)
    assert not any(f.value == "synthetic-49" for a in state.accounts for f in a.fields)
    assert sum(a.kind == "account" for a in state.accounts) == 2
    lines[23] = "unmapped-content"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        convert(path)
