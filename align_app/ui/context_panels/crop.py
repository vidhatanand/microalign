from __future__ import annotations

from PyQt5 import QtWidgets  # type: ignore

from .common import row_container


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Crop Source:"))
    rb_src = QtWidgets.QRadioButton("Source")
    rb_al = QtWidgets.QRadioButton("Aligned")
    if mw.canvas.crop_from_aligned:
        rb_al.setChecked(True)
    else:
        rb_src.setChecked(True)
    rb_src.toggled.connect(
        lambda v: setattr(mw.canvas, "crop_from_aligned", not bool(v))
    )
    lay.addWidget(rb_src)
    lay.addWidget(rb_al)
    btn = QtWidgets.QToolButton()
    btn.setText("Start Crop")
    btn.clicked.connect(lambda: mw.canvas.start_crop_mode(mw.canvas.crop_from_aligned))
    lay.addWidget(btn)
    return w
