from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, label


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()

    lay.addWidget(label("Overlay", w.font()))

    cb_outline = QtWidgets.QCheckBox("Outline")
    cb_outline.setChecked(mw.canvas.show_outline)
    cb_outline.toggled.connect(
        lambda v: (setattr(mw.canvas, "show_outline", bool(v)), mw.canvas.update())
    )
    lay.addWidget(cb_outline)

    cb_overlay = QtWidgets.QCheckBox("Overlay")
    cb_overlay.setChecked(mw.canvas.overlay_mode)
    lay.addWidget(cb_overlay)

    # consistent spacing between checkbox and slider
    lay.addSpacing(12)

    lay.addWidget(label("Alpha", w.font()))
    sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    sld.setRange(0, 100)
    sld.setFixedWidth(160)
    sld.setValue(int(round(mw.canvas.alpha * 100)))
    sld.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "alpha", v / 100.0), mw.canvas.update())
    )
    lay.addWidget(sld)

    # toggle visibility & repaint
    cb_overlay.toggled.connect(
        lambda v: (setattr(mw.canvas, "overlay_mode", bool(v)), mw.canvas.update())
    )
    return w
