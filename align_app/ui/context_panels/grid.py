from __future__ import annotations

from PyQt5 import QtWidgets  # type: ignore

from .common import row_container, gear_button


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Grid:"))

    cb = QtWidgets.QCheckBox("Show Grid")
    cb.setChecked(mw.canvas.grid_on)
    cb.toggled.connect(
        lambda v: (setattr(mw.canvas, "grid_on", bool(v)), mw.canvas.update())
    )
    lay.addWidget(cb)

    lay.addStretch(1)

    def open_settings() -> None:
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle("Grid settings")
        form = QtWidgets.QFormLayout(dlg)

        sp = QtWidgets.QSpinBox()
        sp.setRange(5, 400)
        sp.setValue(mw.canvas.grid_step)
        form.addRow("Grid step (px):", sp)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            mw.canvas.grid_step = int(sp.value())
            mw.canvas.update()
            mw._update_ctx_info()  # type: ignore[attr-defined]

    lay.addWidget(gear_button(mw, open_settings))
    return w
