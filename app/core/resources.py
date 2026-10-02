"""Ресурсы исходников; пути будущей portable-сборки без зависимости от cwd."""
import sys
from pathlib import Path

from app.core.settings import ROOT

APP_USER_MODEL_ID = "frommer.keyshelf.desktop.1"


def resource_path(name):
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
    candidates = [base / name]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Ресурс приложения отсутствует: {name}")
