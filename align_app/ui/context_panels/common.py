from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore


def row_container(font) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.setAlignment(QtCore.Qt.AlignLeft)
    w.setFont(font)
    return w


def gear_button(parent, on_click) -> QtWidgets.QToolButton:
    """Tiny 'settings' button for each panel."""
    btn = QtWidgets.QToolButton(parent)
    btn.setText("⚙")
    btn.setToolTip("Settings")
    btn.clicked.connect(on_click)
    return btn


def ensure_attr(obj, name: str, default) -> None:
    if not hasattr(obj, name):
        setattr(obj, name, default)
