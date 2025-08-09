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


def label(txt: str, font) -> QtWidgets.QLabel:
    lab = QtWidgets.QLabel(txt)
    lab.setFont(font)  # same size as buttons
    return lab


def right_group(parent) -> QtWidgets.QWidget:
    """A right-aligned container for info text + gear."""
    host = QtWidgets.QWidget(parent)
    lay = QtWidgets.QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.setAlignment(QtCore.Qt.AlignRight)
    return host


def gear_button(parent, on_click) -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton(parent)
    btn.setText("⚙")
    btn.setToolTip("Settings")
    btn.clicked.connect(on_click)
    return btn


def ensure_attr(obj, name: str, default) -> None:
    if not hasattr(obj, name):
        setattr(obj, name, default)
