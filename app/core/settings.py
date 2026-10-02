import copy
import json
import os
import sys
from pathlib import Path

from app.services.ui_scale import normalize_delta, stepped

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
DEFAULTS = dict(window_pos_x=100, window_pos_y=100, window_width=1120,
                window_height=780, maximized=False, splitter=[240, 840],
                recent_vaults=[], autostart_enabled=False, start_minimized=False,
                service_type_filters={}, ui_scale_mode="auto",
                ui_scale_delta_percent=0, ui_scale_percent=100,
                window_mode="maxi", mini_pos_x=160, mini_pos_y=160,
                mini_width=640, mini_height=480)


class Settings:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / "settings.json")
        self.data = copy.deepcopy(DEFAULTS)
        data = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for key, default in DEFAULTS.items():
                if key in data and type(data[key]) is type(default):
                    self.data[key] = data[key]
        except (OSError, ValueError, TypeError):
            pass
        if not isinstance(data, dict):
            data = {}
        delta = data.get("ui_scale_delta_percent")
        if "ui_scale_delta_percent" not in data:
            legacy = data.get("ui_scale_percent", 100)
            delta = legacy - 100 if type(legacy) in (int, float) else 0
        self.data.update(ui_scale_mode="auto", ui_scale_delta_percent=normalize_delta(delta),
                         ui_scale_percent=stepped(data.get("ui_scale_percent"), 5, 35, 300, 100))
        for key, limits in {"window_width": (320, 12000),
                            "window_height": (220, 8000),
                            "mini_width": (320, 12000),
                            "mini_height": (120, 8000)}.items():
            self.data[key] = max(limits[0], min(limits[1], self.data[key]))
        if self.data["window_mode"] not in ("maxi", "mini"):
            self.data["window_mode"] = "maxi"
        if len(self.data["splitter"]) != 2 or any(type(x) is not int or x < 0 for x in self.data["splitter"]):
            self.data["splitter"] = [240, 840]
        self.data["recent_vaults"] = list(dict.fromkeys(
            p for p in self.data["recent_vaults"] if isinstance(p, str) and p.strip() and "\x00" not in p and Path(p).is_absolute()))[:10]
        self.data["service_type_filters"] = {
            vault: {service: [kind for kind in ("api", "account", "other") if kind in kinds]
                    for service, kinds in services.items()
                    if isinstance(service, str) and isinstance(kinds, list)}
            for vault, services in self.data["service_type_filters"].items()
            if isinstance(vault, str) and isinstance(services, dict)
        }

    def service_filters(self, path, service):
        vault = os.path.normcase(str(Path(path).resolve()))
        return list(self.data["service_type_filters"].get(vault, {}).get(service, []))

    def remember_service_filters(self, path, service, kinds):
        vault = os.path.normcase(str(Path(path).resolve()))
        services = self.data["service_type_filters"].setdefault(vault, {})
        services[service] = [kind for kind in ("api", "account", "other") if kind in kinds]
        self.save()

    def remember_vault(self, path):
        path = str(Path(path).resolve())
        old = [p for p in self.data["recent_vaults"] if os.path.normcase(p) != os.path.normcase(path)]
        self.data["recent_vaults"] = [path, *old][:10]
        self.save()

    def save(self):
        temp = self.path.with_suffix(".json.tmp")
        try:
            temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.path)
        except OSError:
            temp.unlink(missing_ok=True)


def default_vault_path():
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SecretVault" / "Хранилище.kdbx"


def validate_vault_path(path):
    path = Path(path).expanduser().resolve()
    if path.is_relative_to(ROOT):
        raise ValueError("Выберите папку вне каталога приложения, чтобы сохранить данные при его удалении.")
    if path.suffix.lower() != ".kdbx":
        raise ValueError("Файл хранилища должен иметь расширение .kdbx.")
    return path
