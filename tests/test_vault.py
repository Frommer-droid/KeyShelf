import io
from pathlib import Path

import pytest
from pykeepass import PyKeePass

from app.core.models import Account, Field, search
from app.services.vault import META, Vault, VaultError

PASSWORD = "synthetic-test-passphrase-123"


@pytest.fixture
def vault(tmp_path):
    repo, _ = Vault.create(tmp_path / "test.kdbx", PASSWORD)
    yield repo
    repo.close()


def example(repo):
    result = repo.service("OpenAI")
    service = next(s for s in result.services if s.name == "OpenAI")
    return Account(service_id=service.id, title="Рабочий аккаунт", login="demo@example.invalid",
                   project="Проект Альфа", tags="тест работа", favorite=True, notes="Синтетика",
                   fields=[Field("Основной ключ", "synthetic-main-value"),
                           Field("Тестовый ключ", "synthetic-test-value"),
                           Field("Адрес", "example.invalid", False)])


def test_round_trip_and_protection(vault):
    account = example(vault)
    state = vault.account(account)
    raw = vault.path.read_bytes()
    for plaintext in [account.title, account.login, account.project, account.fields[0].value]:
        assert plaintext.encode() not in raw
    database = PyKeePass(io.BytesIO(raw), password=PASSWORD)
    assert database.version == (4, 0)
    assert database.kdf_algorithm == "argon2id"
    assert database.encryption_algorithm == "aes256"
    params = database.kdbx.header.value.dynamic_header.kdf_parameters.data.dict
    assert params["M"].value == 64 * 1024 * 1024
    assert params["I"].value == 3
    entry = database.entries[0]
    assert entry.is_custom_property_protected(META)
    assert sum(entry.is_custom_property_protected(k) for k in entry.custom_properties) == 3
    vault.close()
    reopened, new_state = Vault.open(vault.path, PASSWORD)
    try:
        assert state == new_state
        assert new_state.accounts[0].fields == account.fields
    finally:
        reopened.close()


def test_wrong_password_and_corruption_preserve_file(vault, tmp_path):
    path = vault.path
    vault.close()
    raw = path.read_bytes()
    with pytest.raises(VaultError, match="пароль"):
        Vault.open(path, "incorrect-synthetic")
    assert path.read_bytes() == raw
    damaged = tmp_path / "damaged.kdbx"
    damaged.write_bytes(raw[:100])
    with pytest.raises(VaultError):
        Vault.open(damaged, PASSWORD)
    assert damaged.read_bytes() == raw[:100]


def test_backups_edit_delete_search(vault, tmp_path):
    account = example(vault)
    state = vault.account(account)
    original = state.accounts[0]
    before = vault.path.read_bytes()
    original.title = "Изменённый"
    original.fields.append(Field("Ещё один", "synthetic-extra"))
    state = vault.account(original)
    assert Path(str(vault.path) + ".bak").read_bytes() == before
    assert search(state, "openai альфа ещё")
    assert not search(state, "synthetic-extra")
    assert not search(state, "example.invalid", "missing-service")
    assert len(search(state, "", favorites=True)) == 1
    backup, backup_state = Vault.open(Path(str(vault.path) + ".bak"), PASSWORD)
    backup.close()
    assert backup_state.accounts[0].title == account.title
    assert len(backup_state.accounts[0].fields) == 3
    copy_path = tmp_path / "copy.kdbx"
    vault.export_backup(copy_path)
    assert copy_path.read_bytes() == vault.path.read_bytes()
    with pytest.raises(FileExistsError):
        vault.export_backup(copy_path)
    assert not vault.account(state.accounts[0], delete=True).accounts


def test_failed_replace_keeps_original(vault, monkeypatch):
    import app.services.vault as module
    before = vault.path.read_bytes()
    original_replace = module.os.replace

    def fail(source, destination):
        if Path(destination) == vault.path:
            raise OSError("synthetic failure")
        original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError):
        vault.service("Never committed")
    assert vault.path.read_bytes() == before
    assert not list(vault.path.parent.glob(".vault-*"))
    assert not list(vault.path.parent.glob(".backup-*"))


def test_external_changes_and_exclusive_open(vault):
    with pytest.raises(VaultError, match="экземпляром"):
        Vault.open(vault.path, PASSWORD)
    with pytest.raises(VaultError, match="существует"):
        # Блокировка может сработать раньше проверки существующего файла.
        vault.close()
        Vault.create(vault.path, PASSWORD)
    reopened, _ = Vault.open(vault.path, PASSWORD)
    try:
        vault.path.write_bytes(vault.path.read_bytes() + b"changed")
        with pytest.raises(VaultError, match="изменён"):
            reopened.service("No overwrite")
        assert vault.path.read_bytes().endswith(b"changed")
    finally:
        reopened.close()


def test_service_rename_and_delete(vault):
    state = vault.account(example(vault))
    service_id = state.accounts[0].service_id
    state = vault.service("Новый сервис", service_id)
    assert state.accounts[0].service == "Новый сервис"
    state = vault.service("", service_id, delete=True)
    assert not state.accounts
