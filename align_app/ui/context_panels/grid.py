from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, label


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(label("Grid", w.font()))

    cb = QtWidgets.QCheckBox("Show")
    cb.setChecked(mw.canvas.grid_on)
    cb.toggled.connect(
        lambda v: (setattr(mw.canvas, "grid_on", bool(v)), mw.canvas.update())
    )
    lay.addWidget(cb)

    lay.addSpacing(12)

    sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    sld.setRange(5, 400)
    sld.setValue(int(mw.canvas.grid_step))
    sld.setFixedWidth(160)
    sld.setSingleStep(1)
    sld.setPageStep(10)
    sld.setToolTip("Grid step (px)")
    sld.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "grid_step", int(v)), mw.canvas.update())
    )
    lay.addWidget(sld)

    return w
