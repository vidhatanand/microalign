from __future__ import annotations

from PyQt5 import QtWidgets  # type: ignore

from .common import row_container, gear_button, ensure_attr


def build(mw) -> QtWidgets.QWidget:
    canvas = mw.canvas
    ensure_attr(canvas, "step", getattr(canvas, "step", 1.0))
    ensure_attr(canvas, "micro_step", max(0.05, canvas.step / 4.0))

    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Move:"))

    def add_move_btn(label: str, dx: int, dy: int, mult: float) -> None:
        btn = QtWidgets.QToolButton()
        btn.setText(label)
        btn.clicked.connect(
            lambda: canvas.move_dxdy(dx * canvas.step * mult, dy * canvas.step * mult)
        )
        lay.addWidget(btn)

    # normal step
    add_move_btn("←", -1, 0, 1.0)
    add_move_btn("→", +1, 0, 1.0)
    add_move_btn("↑", 0, -1, 1.0)
    add_move_btn("↓", 0, +1, 1.0)

    # micro step
    def add_micro_btn(label: str, dx: int, dy: int) -> None:
        btn = QtWidgets.QToolButton()
        btn.setText(label)
        btn.clicked.connect(
            lambda: canvas.move_dxdy(dx * canvas.micro_step, dy * canvas.micro_step)
        )
        lay.addWidget(btn)

    add_micro_btn("µ←", -1, 0)
    add_micro_btn("µ→", +1, 0)
    add_micro_btn("µ↑", 0, -1)
    add_micro_btn("µ↓", 0, +1)

    lay.addStretch(1)

    def open_settings() -> None:
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle("Move settings")
        form = QtWidgets.QFormLayout(dlg)

        step = QtWidgets.QDoubleSpinBox()
        step.setDecimals(1)
        step.setRange(0.5, 50.0)
        step.setSingleStep(0.5)
        step.setValue(canvas.step)

        micro = QtWidgets.QDoubleSpinBox()
        micro.setDecimals(2)
        micro.setRange(0.05, 10.0)
        micro.setSingleStep(0.05)
        micro.setValue(canvas.micro_step)

        form.addRow("Step (px):", step)
        form.addRow("Micro step (px):", micro)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            canvas.step = float(step.value())
            canvas.micro_step = float(micro.value())
            mw._update_ctx_info()  # type: ignore[attr-defined]

    lay.addWidget(gear_button(mw, open_settings))
    return w
