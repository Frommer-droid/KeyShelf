"""Keep original metrics so repeated scaling never compounds."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QLayout, QWidget

MAX_SIZE = 16777215


def metrics(root, factor, capture_only=False):
    widgets = [root, *root.findChildren(QWidget)]
    for widget in widgets:
        base = widget.property("uiScaleBaseline")
        if base is None:
            margins = widget.contentsMargins()
            base = {"margins": [margins.left(), margins.top(), margins.right(), margins.bottom()],
                    "min": [widget.minimumWidth(), widget.minimumHeight()],
                    "max": [widget.maximumWidth(), widget.maximumHeight()]}
            if isinstance(widget, QAbstractButton):
                base["icon"] = [widget.iconSize().width(), widget.iconSize().height()]
            widget.setProperty("uiScaleBaseline", base)
        if capture_only:
            continue
        widget.setContentsMargins(*(round(value * factor) for value in base["margins"]))
        maximum = [round(v * factor) if v < MAX_SIZE else MAX_SIZE for v in base["max"]]
        minimum = [round(v * factor) for v in base["min"]]
        widget.setMaximumSize(*maximum)
        widget.setMinimumSize(*minimum)
        if "icon" in base:
            widget.setIconSize(QSize(*(max(1, round(v * factor)) for v in base["icon"])))
            if widget.property("uiSquareButton"):
                widget.setFixedWidth(widget.sizeHint().height())
            else:
                widget.setMinimumWidth(max(widget.minimumWidth(), widget.sizeHint().height()))
    for layout in root.findChildren(QLayout):
        base = layout.property("uiScaleBaseline")
        if base is None:
            margins = layout.contentsMargins()
            base = {"margins": [margins.left(), margins.top(), margins.right(), margins.bottom()],
                    "spacing": layout.spacing()}
            if isinstance(layout, QGridLayout):
                base.update(horizontal=layout.horizontalSpacing(), vertical=layout.verticalSpacing())
            layout.setProperty("uiScaleBaseline", base)
        if capture_only:
            continue
        layout.setContentsMargins(*(round(value * factor) for value in base["margins"]))
        layout.setSpacing(round(base["spacing"] * factor) if base["spacing"] >= 0 else -1)
        if isinstance(layout, QGridLayout):
            for name, setter in [("horizontal", layout.setHorizontalSpacing), ("vertical", layout.setVerticalSpacing)]:
                value = base[name]
                setter(round(value * factor) if value >= 0 else -1)
