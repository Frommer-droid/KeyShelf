"""KDBX4: операции выполняются последовательно в рабочем потоке."""
import hashlib
import io
import json
import os
import tempfile
import uuid
from pathlib import Path

from pykeepass import PyKeePass
from pykeepass.exceptions import CredentialsError, HeaderChecksumError, PayloadChecksumError
from pykeepass.kdbx_parsing.kdbx4 import kdf_uuids
from pykeepass.pykeepass import BLANK_DATABASE_LOCATION, BLANK_DATABASE_PASSWORD

from app.core.models import Account, Field, Service, Snapshot
from app.services.exchange import document, identity, parse

META = "SecretVault.Metadata.v1"
PREFIX = "SecretVault.Field."


class VaultError(Exception):
    pass


class FileGuard:
    """Межпроцессная блокировка. Пустой sidecar не содержит данных."""
    def __init__(self, path):
        self.file = open(str(path) + ".lock", "a+b")
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise VaultError("Этот файл уже открыт другим экземпляром приложения.") from None

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).digest()


def snapshot(kp):
    services = [Service(str(g.uuid), g.name or "Без названия") for g in kp.groups
                if g != kp.root_group or g.entries]
    accounts = []
    for e in kp.entries:
        props = e.custom_properties
        try:
            meta = json.loads(props.get(META, "{}"))
            if not isinstance(meta, dict):
                raise ValueError
            order = meta.get("field_layout")
            if order is not None and (not isinstance(order, list)
                                      or any(not isinstance(name, str) for name in order)
                                      or len(set(order)) != len(order)):
                raise ValueError
            fields = [Field(str(f["label"]), props.get(f["key"]) or "",
                            e.is_custom_property_protected(f["key"])) for f in meta.get("fields", [])]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise VaultError("Не удалось прочитать описание полей. Файл не изменён.") from None
        managed = {f["key"] for f in meta.get("fields", [])}
        if e.password:
            fields.insert(0, Field("Пароль", e.password, True))
        if e.url:
            fields.append(Field("URL", e.url, False))
        for key, value in props.items():
            if key != META and key not in managed:
                fields.append(Field(key, value, e.is_custom_property_protected(key)))
        g = e.group
        accounts.append(Account(str(e.uuid), str(g.uuid), g.name or "Без названия",
                                e.title or "Без названия", e.username or "",
                                str(meta.get("project", "")), str(meta.get("tags", "")),
                                e.notes or "", bool(meta.get("favorite", False)), fields,
                                str(meta.get("kind", "legacy")), bool(meta.get("api_paid", False)),
                                meta.get("field_layout")))
    return Snapshot(services, accounts)


class Vault:
    def __init__(self, path, password, guard, digest):
        self.path = Path(path)
        self.password = password
        self.guard = guard
        self.digest = digest

    @classmethod
    def open(cls, path, password):
        path = Path(path)
        if not path.is_file():
            raise VaultError("Файл не найден. Выберите существующее хранилище.")
        guard = FileGuard(path)
        try:
            raw = path.read_bytes()
            kp = cls.decode(raw, password)
            result = snapshot(kp)
            return cls(path, password, guard, hashlib.sha256(raw).digest()), result
        except BaseException:
            guard.close()
            raise

    @classmethod
    def create(cls, path, password):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        guard = FileGuard(path)
        temp = None
        try:
            if path.exists():
                raise VaultError("Файл уже существует. Откройте его или выберите другое имя.")
            kp = PyKeePass(BLANK_DATABASE_LOCATION, password=BLANK_DATABASE_PASSWORD)
            kp.password = password
            kp.database_name = "KeyShelf"
            params = kp.kdbx.header.value.dynamic_header.kdf_parameters.data.dict
            params["$UUID"].value = kdf_uuids["argon2id"]
            params["I"].value = 3
            params["M"].value = 64 * 1024 * 1024
            params["P"].value = 2
            params["V"].value = 19
            temp = cls.write_verified(kp, path, password)
            # Создание без перезаписи даже при гонке с другим процессом.
            os.link(temp, path)
            return cls(path, password, guard, fingerprint(path)), snapshot(kp)
        except BaseException:
            guard.close()
            raise
        finally:
            if temp:
                temp.unlink(missing_ok=True)

    @staticmethod
    def decode(raw, password):
        try:
            kp = PyKeePass(io.BytesIO(raw), password=password)
            if kp.version != (4, 0):
                raise VaultError("Поддерживается KDBX4. Преобразуйте копию файла в KeePassXC.")
            return kp
        except CredentialsError:
            raise VaultError("Мастер-пароль не подошёл либо нарушена целостность файла. Файл не изменён.") from None
        except (HeaderChecksumError, PayloadChecksumError):
            raise VaultError("Нарушена целостность хранилища. Откройте резервную копию.") from None
        except VaultError:
            raise
        except Exception:
            raise VaultError("Не удалось прочитать KDBX4: файл повреждён или имеет неподдерживаемый формат.") from None

    @staticmethod
    def write_verified(kp, path, password):
        fd, name = tempfile.mkstemp(prefix=".vault-", suffix=".kdbx", dir=path.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "w+b") as stream:
                kp.save(stream)
                stream.flush()
                os.fsync(stream.fileno())
            verified = Vault.decode(temp.read_bytes(), password)
            if snapshot(verified) != snapshot(kp):
                raise VaultError("Проверка сохранённых данных не прошла. Исходный файл не изменён.")
            return temp
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def transact(self, operation):
        if not self.password:
            raise VaultError("Хранилище заблокировано.")
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).digest() != self.digest:
            raise VaultError("Файл изменён другой программой. Заблокируйте и откройте его снова.")
        kp = self.decode(raw, self.password)
        operation(kp)
        temp = self.write_verified(kp, self.path, self.password)
        backup_temp = None
        try:
            if fingerprint(self.path) != self.digest:
                raise VaultError("Файл изменён во время сохранения. Изменения не записаны.")
            backup = Path(str(self.path) + ".bak")
            fd, name = tempfile.mkstemp(prefix=".backup-", suffix=".kdbx", dir=self.path.parent)
            backup_temp = Path(name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(backup_temp, backup)
            os.replace(temp, self.path)
            self.digest = fingerprint(self.path)
            return snapshot(kp)
        finally:
            temp.unlink(missing_ok=True)
            if backup_temp:
                backup_temp.unlink(missing_ok=True)

    def close(self):
        self.password = None
        self.digest = None
        self.guard.close()

    def service(self, name, id=None, delete=False):
        def operation(kp):
            g = kp.find_groups(uuid=uuid.UUID(id), first=True) if id else None
            if delete:
                if g == kp.root_group:
                    raise VaultError("Корневую группу удалить нельзя.")
                kp.delete_group(g)
                return
            if not name.strip():
                raise VaultError("Укажите название сервиса.")
            if any(x.name.casefold() == name.strip().casefold() and x != g for x in kp.groups):
                raise VaultError("Сервис с таким названием уже существует.")
            if g:
                g.name = name.strip()
            else:
                kp.add_group(kp.root_group, name.strip())
        return self.transact(operation)

    def account(self, account, delete=False):
        def operation(kp):
            e = kp.find_entries(uuid=uuid.UUID(account.id), first=True) if account.id else None
            if delete:
                kp.delete_entry(e)
                return
            if not account.title.strip():
                raise VaultError("Укажите название аккаунта.")
            g = kp.find_groups(uuid=uuid.UUID(account.service_id), first=True)
            if not g:
                raise VaultError("Сервис не найден.")
            if e:
                # Не удаляем историю/вложения импортированной записи.
                kp.move_entry(e, g)
                e.title, e.username = account.title.strip(), account.login
                for key in list(e.custom_properties):
                    e.delete_custom_property(key)
                e.password = ""
                e.url = ""
            else:
                e = kp.add_entry(g, account.title.strip(), account.login, "", force_creation=True)
            self.write_fields(e, account)
        return self.transact(operation)

    @staticmethod
    def write_fields(entry, account):
        entry.notes = account.notes
        fields = []
        for f in account.fields:
            key = PREFIX + str(uuid.uuid4())
            entry.set_custom_property(key, f.value, protect=f.secret)
            fields.append(dict(key=key, label=f.label))
        entry.set_custom_property(META, json.dumps(dict(project=account.project, tags=account.tags,
                                  favorite=account.favorite, fields=fields, kind=account.kind, api_paid=account.api_paid,
                                  field_layout=account.field_layout), ensure_ascii=False), protect=True)
        entry.touch(modify=True)

    def import_records(self, incoming):
        incoming = parse(document(incoming))
        counts = {"added": 0, "skipped": 0, "services": 0}

        def operation(kp):
            current = snapshot(kp)
            groups = {s.name.casefold(): kp.find_groups(uuid=uuid.UUID(s.id), first=True) for s in current.services}
            existing = {(a.service.casefold(), identity(a)) for a in current.accounts}
            for service in incoming.services:
                name = service.name.casefold()
                group = groups.get(name)
                if group is None:
                    group = kp.add_group(kp.root_group, service.name)
                    groups[name] = group
                    counts["services"] += 1
                for account in incoming.accounts:
                    if account.service_id != service.id:
                        continue
                    key = (name, identity(account))
                    if key in existing:
                        counts["skipped"] += 1
                        continue
                    entry = kp.add_entry(group, account.title.strip(), account.login, "", force_creation=True)
                    self.write_fields(entry, account)
                    existing.add(key)
                    counts["added"] += 1
        return self.transact(operation), counts

    def export_backup(self, destination):
        """Экспорт текущего шифрованного файла без перезаписи назначения."""
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).digest() != self.digest:
            raise VaultError("Файл изменён. Откройте его повторно перед копированием.")
        destination = Path(destination)
        fd, name = tempfile.mkstemp(prefix=".copy-", suffix=".kdbx", dir=destination.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
