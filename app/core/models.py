from dataclasses import dataclass, field

BASE_FIELD_LABELS = {
    "api": ("API-ключ",),
    "account": ("Пароль", "Секрет 2FA"),
    "other": ("Поле 1", "Поле 2", "Поле 3"),
}
EXTRA_FIELD_PREFIX = "Дополнительное поле "


@dataclass
class Field:
    label: str
    value: str
    secret: bool = True


@dataclass
class Account:
    id: str = ""
    service_id: str = ""
    service: str = ""
    title: str = ""
    login: str = ""
    project: str = ""
    tags: str = ""
    notes: str = ""
    favorite: bool = False
    fields: list[Field] = field(default_factory=list)
    kind: str = "legacy"
    api_paid: bool = False
    field_layout: list[str] | None = None


@dataclass
class Service:
    id: str
    name: str


@dataclass
class Snapshot:
    services: list[Service] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)


def search(snapshot, query, service_id=None, favorites=False):
    words = query.casefold().split()
    result = []
    for a in snapshot.accounts:
        if service_id and a.service_id != service_id:
            continue
        if favorites and not a.favorite:
            continue
        # Never index field values, including nonsecret custom fields or notes.
        text = " ".join([a.service, a.title, a.login, a.project, a.tags,
                         *[f.label for f in a.fields]]).casefold()
        if all(word in text for word in words):
            result.append(a)
    return sorted(result, key=lambda a: (not a.favorite, a.title.casefold()))
