# -*- coding: utf-8 -*-
"""Обязательная тема приложения."""

from app.ui.theme.colors import THEME_COLORS
from app.ui.theme.scale import scale_point_size, scale_px
from app.ui.theme.styles import (
    DERIVED_COLORS,
    apply_theme,
    build_global_stylesheet,
    enforce_button_proportions,
)

__all__ = [
    "DERIVED_COLORS",
    "THEME_COLORS",
    "apply_theme",
    "build_global_stylesheet",
    "enforce_button_proportions",
    "scale_point_size",
    "scale_px",
]
