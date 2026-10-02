"""Versioned plaintext exchange; diagnostics never contain record values."""
import json
import os
import tempfile
from pathlib import Path

from app.core.models import BASE_FIELD_LABELS, EXTRA_FIELD_PREFIX, Account, Field, Service, Snapshot

FORMAT = "acc-storage-exchange"
MAX_BYTES = 10 * 1024 * 1024


class ExchangeError(ValueError):
    pass


def document(state):
    return {"format": FORMAT, "version": 1, "services": [
        {"name": s.name, "records": [
            {"kind": a.kind, "label": a.title, "login": a.login,
             "comment": a.notes, "project": a.project, "tags": a.tags,
             **({"field_layout": a.field_layout} if a.field_layout is not None else {}),
             "favorite": a.favorite, "api_paid": a.api_paid, "fields": [
                 {"label": f.label, "value": f.value, "secret": f.secret} for f in a.fields]}
            for a in state.accounts if a.service_id == s.id]}
        for s in state.services]}


def parse(data):
    try:
        if set(data) != {"format", "version", "services"} or data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != 1:
            raise ValueError
        if not isinstance(data["services"], list):
            raise ValueError
        state = Snapshot()
        names = set()
        for i, service in enumerate(data["services"]):
            if set(service) != {"name", "records"} or not isinstance(service["name"], str) or not service["name"].strip() or not isinstance(service["records"], list):
                raise ValueError
            name = service["name"].strip()
            if name.casefold() in names:
                raise ValueError
            names.add(name.casefold())
            s = Service(str(i), name)
            state.services.append(s)
            for r in service["records"]:
                required = {"kind", "label", "login", "comment", "project", "tags", "favorite", "fields"}
                if not required.issubset(r) or set(r) - required - {"api_paid", "field_layout"} or type(r.get("api_paid", False)) is not bool:
                    raise ValueError
                if any(not isinstance(r[k], str) for k in ("kind", "label", "login", "comment", "project", "tags")) or not r["label"].strip() or r["kind"] not in ("api", "account", "other", "legacy") or type(r["favorite"]) is not bool or not isinstance(r["fields"], list):
                    raise ValueError
                fields = []
                for f in r["fields"]:
                    if set(f) != {"label", "value", "secret"} or not isinstance(f["label"], str) or not f["label"].strip() or not isinstance(f["value"], str) or type(f["secret"]) is not bool:
                        raise ValueError
                    fields.append(Field(f["label"], f["value"], f["secret"]))
                if r["kind"] != "legacy":
                    expected = set(BASE_FIELD_LABELS[r["kind"]])
                    labels = [f.label for f in fields]
                    extras = [name for name in labels if name not in expected]
                    if (not expected.issubset(labels) or len(set(labels)) != len(labels)
                            or extras != [f"{EXTRA_FIELD_PREFIX}{i}" for i in range(1, len(extras) + 1)]
                            or not all(f.secret for f in fields)):
                        raise ValueError
                order = r.get("field_layout")
                if order is not None:
                    values = {f.label: f.value for f in fields}
                    if r["kind"] == "account":
                        values["Логин"] = r["login"]
                    if (not isinstance(order, list) or any(not isinstance(name, str) for name in order)
                            or len(set(order)) != len(order) or not set(order).issubset(values)
                            or any(value for name, value in values.items() if name not in order)
                            or any(f.label.startswith(EXTRA_FIELD_PREFIX) and f.label not in order for f in fields)):
                        raise ValueError
                state.accounts.append(Account(service_id=s.id, service=s.name, title=r["label"].strip(), login=r["login"], notes=r["comment"], project=r["project"], tags=r["tags"], favorite=r["favorite"], kind=r["kind"], fields=fields, api_paid=r.get("api_paid", False), field_layout=order))
                if len(state.accounts) > 10000:
                    raise ValueError
        return state
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ExchangeError("Неверный формат файла обмена или неподдерживаемая версия. Данные не изменены.") from None


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def read_exchange(path):
    try:
        with open(path, "rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError
        return parse(json.loads(raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicates))
    except ExchangeError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise ExchangeError("Не удалось прочитать файл обмена UTF-8 JSON (максимум 10 МиБ). Данные не изменены.") from None


def write_exchange(path, state):
    path = Path(path)
    raw = json.dumps(document(state), ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ExchangeError("Экспорт превышает допустимые 10 МиБ.")
    parse(json.loads(raw))
    temp = None
    try:
        fd, name = tempfile.mkstemp(prefix=".exchange-", suffix=".tmp", dir=path.parent)
        temp = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        read_exchange(temp)
        os.link(temp, path)
    except OSError:
        raise ExchangeError("Не удалось сохранить файл обмена. Выберите новое имя в доступной папке; существующий файл не перезаписывается.") from None
    finally:
        if temp:
            temp.unlink(missing_ok=True)


def identity(account):
    order = account.field_layout
    if order is None:
        order = (["Логин"] if account.kind == "account" else []) + [f.label for f in account.fields]
    return (account.kind, account.title, account.login, account.notes, account.project, account.tags,
            tuple(sorted((f.label, f.value, f.secret) for f in account.fields)), tuple(order))
