from __future__ import annotations

from PyQt5 import QtWidgets  # type: ignore

from .common import row_container, gear_button, ensure_attr


def build(mw) -> QtWidgets.QWidget:
    canvas = mw.canvas
    ensure_attr(canvas, "rot_step", getattr(canvas, "rot_step", 0.25))
    ensure_attr(canvas, "micro_rot_step", max(0.001, canvas.rot_step / 4.0))

    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Rotate:"))

    # normal rotation
    b1 = QtWidgets.QToolButton()
    b1.setText("Rot−")
    b1.clicked.connect(lambda: canvas.rotate_deg(-canvas.rot_step))
    lay.addWidget(b1)

    b2 = QtWidgets.QToolButton()
    b2.setText("Rot+")
    b2.clicked.connect(lambda: canvas.rotate_deg(+canvas.rot_step))
    lay.addWidget(b2)

    # micro rotation
    mb1 = QtWidgets.QToolButton()
    mb1.setText("µRot−")
    mb1.clicked.connect(lambda: canvas.rotate_deg(-canvas.micro_rot_step))
    lay.addWidget(mb1)

    mb2 = QtWidgets.QToolButton()
    mb2.setText("µRot+")
    mb2.clicked.connect(lambda: canvas.rotate_deg(+canvas.micro_rot_step))
    lay.addWidget(mb2)

    lay.addStretch(1)

    def open_settings() -> None:
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle("Rotate settings")
        form = QtWidgets.QFormLayout(dlg)

        rot = QtWidgets.QDoubleSpinBox()
        rot.setDecimals(2)
        rot.setRange(0.01, 5.0)
        rot.setSingleStep(0.05)
        rot.setSuffix("°")
        rot.setValue(canvas.rot_step)

        mrot = QtWidgets.QDoubleSpinBox()
        mrot.setDecimals(3)
        mrot.setRange(0.001, 1.0)
        mrot.setSingleStep(0.005)
        mrot.setSuffix("°")
        mrot.setValue(canvas.micro_rot_step)

        form.addRow("Step:", rot)
        form.addRow("Micro step:", mrot)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            canvas.rot_step = float(rot.value())
            canvas.micro_rot_step = float(mrot.value())
            mw._update_ctx_info()  # type: ignore[attr-defined]

    lay.addWidget(gear_button(mw, open_settings))
    return w
