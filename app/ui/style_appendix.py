import re

from app.ui.theme import THEME_COLORS, scale_point_size

# Дополнительный цвет типа «Другое» по запросу владельца; эталонная палитра неизменна.
DERIVED_COLORS = {"other": "#C6A0DC"}
C = {**THEME_COLORS, **DERIVED_COLORS}


def tint(base, color, amount):
    channels = [round(int(base[i:i + 2], 16) * (1 - amount) + int(color[i:i + 2], 16) * amount) for i in (1, 3, 5)]
    return "#" + "".join(f"{value:02X}" for value in channels)


TYPE_COLORS = {"api": C["accent_hover"], "account": C["success"], "other": C["other"], "favorite": C["warning"]}
TYPE_BACKGROUNDS = {kind: tint(C["surface_alt"], color, 0.12) for kind, color in TYPE_COLORS.items()}


def type_styles():
    rules = [f"""
    QPushButton#typeFilter, QPushButton#typeFilter:hover,
    QPushButton#typeFilter:pressed, QPushButton#typeFilter:focus {{
        border: 1px solid transparent; color: {C['text_strong']}; background: {C['surface_alt']};
    }}
    """]
    for kind, color in TYPE_COLORS.items():
        filter_selector = f'QPushButton#typeFilter[recordKind="{kind}"]'
        rules.append(filter_selector + f":!checked:hover {{ border-color: {color}; }}")
        states = (":checked", ":checked:hover", ":checked:pressed", ":checked:focus", ":checked:hover:focus", ":checked:pressed:focus")
        states += (":!checked:hover", ":!checked:hover:focus", ":!checked:hover:pressed")
        rules.append(", ".join(filter_selector + state for state in states) +
                     f" {{ border: 1px solid {color}; color: {color}; background: {TYPE_BACKGROUNDS[kind]}; }}")
        header = f'QPushButton#cardHeader[recordKind="{kind}"]'
        rules.append(", ".join(header + state for state in ("", ":hover", ":checked", ":pressed", ":focus", ":checked:hover", ":checked:pressed", ":checked:focus")) +
                     f" {{ color: {color}; background: {tint(C['surface_alt'], color, 0.06)}; border: 1px solid {C['border']}; }}")
        rules.append(f'QFrame#accountCard[recordKind="{kind}"] {{ border-left: 2px solid {color}; }}')
        rules.append(filter_selector + f":disabled, {filter_selector}:checked:disabled {{ color: {C['disabled_text']}; background: {C['disabled_background']}; border-color: transparent; }}")
    return "\n".join(rules)


def appendix(scale_factor=1.0):
    # Дополнение для вкладок, панелей и карточек; ядро шаблона не меняется.
    stylesheet = f"""
    QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 7px; }}
    QTabBar::tab {{ background: {C['surface']}; padding: 12px 24px; border: 1px solid {C['border']}; }}
    QTabBar::tab:selected {{ background: {C['surface_alt']}; color: {C['accent']}; }}
    QTabBar::tab:hover {{ background: {C['surface_hover']}; }}
    QTabBar::tab:disabled {{ color: {C['disabled_text']}; }}
    QWidget#servicePanel {{ background: {C['surface']}; border-radius: 7px; }}
    QListWidget {{ background: {C['surface']}; border: 0; outline: 0; }}
    QListWidget::item {{ padding: 12px 10px; margin: 3px 0; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {C['selection']}; color: {C['text_strong']}; }}
    QListWidget::item:hover {{ background: {C['surface_hover']}; }}
    QListWidget::item:focus {{ border: 1px solid {C['focus']}; }}
    QScrollArea {{ border: 0; }}
    QPushButton#addFieldButton {{ min-height: 18px; padding: 6px 0; }}
    QPushButton#apiPriceToggle {{ min-height: 18px; padding: 6px 0; color: {C['success']}; }}
    QPushButton#apiPriceToggle:checked {{ color: {C['warning']}; }}
    QFrame#accountCard {{ background: {C['surface_alt']}; border: 1px solid {C['border']}; border-radius: 8px; }}
    QFrame#accountCard QLabel, QWidget#cardBody {{ background: transparent; }}
    QPushButton#cardHeader {{ text-align: left; background: {C['surface_alt']}; border: 1px solid {C['border']}; color: {C['text_strong']}; }}
    QPushButton#cardHeader:hover {{ background: {C['surface_hover']}; border-color: {C['focus']}; }}
    QPushButton#cardHeader:checked {{ border-color: {C['accent']}; }}
    QPushButton#cardHeader:pressed {{ background: {C['surface_pressed']}; }}
    QPushButton#cardHeader:disabled {{ color: {C['disabled_text']}; }}
    /* Ролевые disabled-состояния имеют приоритет над цветными ролями ядра. */
    QPushButton#danger_btn:disabled, QPushButton#success_btn:disabled,
    QPushButton#warning_btn:disabled {{ color: {C['disabled_text']}; background: {C['disabled_background']}; border-color: {C['disabled_border']}; }}
    QLabel#error {{ color: {C['danger_text']}; }}
    QLabel#apiPaid {{ color: {C['warning']}; font-weight: 600; padding: 2px; }}
    QLabel#apiFree {{ color: {C['success']}; font-weight: 600; padding: 2px; }}
    QLabel#fieldValue {{ color: {C['text_strong']}; }}
    QSplitter::handle:horizontal {{ width: 2px; background: {C['border']}; }}
    {type_styles()}
    """
    def dimension(match):
        value, unit = float(match[1]), match[2]
        scaled = scale_point_size(value, scale_factor) if unit == "pt" else max(0, round(value * scale_factor))
        return f"{scaled:g}{unit}"
    return re.sub(r"(\d+(?:\.\d+)?)(px|pt)\b", dimension, stylesheet)
