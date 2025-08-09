from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, label


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()

    # compact sub-group that stays tight/left
    grp = QtWidgets.QWidget(w)
    grp.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Preferred)
    gl = QtWidgets.QHBoxLayout(grp)
    gl.setContentsMargins(0, 0, 0, 0)
    gl.setSpacing(4)

    gl.addWidget(label("Overlay", w.font()))

    cb_outline = QtWidgets.QCheckBox("Outline")
    cb_outline.setChecked(mw.canvas.show_outline)
    cb_outline.toggled.connect(
        lambda v: (setattr(mw.canvas, "show_outline", bool(v)), mw.canvas.update())
    )
    gl.addWidget(cb_outline)

    cb_overlay = QtWidgets.QCheckBox("Overlay")
    cb_overlay.setChecked(mw.canvas.overlay_mode)
    cb_overlay.toggled.connect(
        lambda v: (setattr(mw.canvas, "overlay_mode", bool(v)), mw.canvas.update())
    )
    gl.addWidget(cb_overlay)

    gl.addWidget(label("Alpha", w.font()))
    sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    sld.setRange(0, 100)
    sld.setFixedWidth(140)
    sld.setValue(int(round(mw.canvas.alpha * 100)))
    sld.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "alpha", v / 100.0), mw.canvas.update())
    )
    gl.addWidget(sld)

    lay.addWidget(grp)
    return w
