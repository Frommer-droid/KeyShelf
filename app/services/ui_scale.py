"""Pure screen-based scale calculations; values are Qt logical pixels."""
import math
from dataclasses import dataclass


def stepped(value, step, low, high, fallback):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        value = fallback
    return max(low, min(high, round(value / step) * step))


def normalize_delta(value):
    return stepped(value, 10, -50, 50, 0)


@dataclass(frozen=True)
class UIScaleState:
    auto_percent: int
    delta_percent: int
    final_percent: int

    @property
    def scale_factor(self):
        return self.final_percent / 100


def calculate_scale(width, height, dpi, delta=0):
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (width, height, dpi)):
        width, height, dpi = 2560, 1440, 96
    ratio = min(width * dpi / 96 / 2560, height * dpi / 96 / 1440)
    auto = stepped(ratio * 100, 10, 70, 200, 100)
    delta = normalize_delta(delta)
    final = stepped(auto + max(auto, 100) * delta / 100, 5, 35, 300, 100)
    return UIScaleState(auto, delta, final)


def resolve_screen(screen, delta=0):
    if screen is None:
        return calculate_scale(2560, 1440, 96, delta)
    area = screen.availableGeometry()
    return calculate_scale(area.width(), area.height(), screen.logicalDotsPerInch(), delta)


def target_window_size(width, height, ratio, hint_width, hint_height, available_width, available_height):
    return (min(available_width, max(hint_width, round(width * ratio))),
            min(available_height, max(hint_height, round(height * ratio))))
