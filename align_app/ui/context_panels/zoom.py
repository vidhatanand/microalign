from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, gear_button, label, right_group


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(label("Zoom", w.font()))

    z1 = QtWidgets.QToolButton()
    z1.setText("Zoom−")
    z1.clicked.connect(lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.scale_step))
    lay.addWidget(z1)

    z2 = QtWidgets.QToolButton()
    z2.setText("Zoom+")
    z2.clicked.connect(lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.scale_step))
    lay.addWidget(z2)

    mz1 = QtWidgets.QToolButton()
    mz1.setText("µZoom−")
    mz1.clicked.connect(lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.micro_scale_step))
    lay.addWidget(mz1)

    mz2 = QtWidgets.QToolButton()
    mz2.setText("µZoom+")
    mz2.clicked.connect(lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.micro_scale_step))
    lay.addWidget(mz2)

    lay.addStretch(1)

    rg = right_group(w)
    rg_lay = rg.layout()
    info = QtWidgets.QLabel("")
    info.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    rg_lay.addWidget(info)

    def refresh_info() -> None:
        z = mw.canvas.scale_step * 100.0
        mz = mw.canvas.micro_scale_step * 100.0
        info.setText(f"Step ±{z:.2f}% | µ {mz:.2f}%")

    def open_settings() -> None:
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle("Zoom settings")
        form = QtWidgets.QFormLayout(dlg)

        zs = QtWidgets.QDoubleSpinBox()
        zs.setDecimals(3)
        zs.setSingleStep(0.001)
        zs.setRange(0.001, 0.05)
        zs.setValue(mw.canvas.scale_step)

        mzs = QtWidgets.QDoubleSpinBox()
        mzs.setDecimals(3)
        mzs.setSingleStep(0.001)
        mzs.setRange(0.0005, 0.02)
        mzs.setValue(mw.canvas.micro_scale_step)

        form.addRow("Step (Δscale):", zs)
        form.addRow("Micro step (Δscale):", mzs)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            mw.canvas.scale_step = float(zs.value())
            mw.canvas.micro_scale_step = float(mzs.value())
            refresh_info()

    rg_lay.addWidget(gear_button(mw, open_settings))
    lay.addWidget(rg)

    refresh_info()
    return w
