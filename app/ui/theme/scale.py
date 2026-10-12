# -*- coding: utf-8 -*-
"""Минимальные helpers масштабирования QSS.

Масштаб рассчитывается по экрану и пользовательской поправке;
значения QSS считаются от базовых метрик без повторного умножения.
"""

from __future__ import annotations


def scale_px(value: int | float, scale_factor: float) -> int:
    return max(1, round(value * scale_factor))


def scale_point_size(value: int | float, scale_factor: float) -> float:
    return max(1.0, round(value * scale_factor * 2) / 2)
