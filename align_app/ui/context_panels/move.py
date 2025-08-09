from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, gear_button, ensure_attr, label, right_group


def build(mw) -> QtWidgets.QWidget:
    canvas = mw.canvas
    ensure_attr(canvas, "step", getattr(canvas, "step", 1.0))
    ensure_attr(canvas, "micro_step", max(0.05, canvas.step / 4.0))

    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(label("Move", w.font()))

    def add_move_btn(txt: str, dx: int, dy: int, mult: float) -> None:
        btn = QtWidgets.QToolButton()
        btn.setText(txt)
        btn.clicked.connect(
            lambda: canvas.move_dxdy(dx * canvas.step * mult, dy * canvas.step * mult)
        )
        lay.addWidget(btn)

    add_move_btn("←", -1, 0, 1.0)
    add_move_btn("→", +1, 0, 1.0)
    add_move_btn("↑", 0, -1, 1.0)
    add_move_btn("↓", 0, +1, 1.0)

    def add_micro_btn(txt: str, dx: int, dy: int) -> None:
        btn = QtWidgets.QToolButton()
        btn.setText(txt)
        btn.clicked.connect(
            lambda: canvas.move_dxdy(dx * canvas.micro_step, dy * canvas.micro_step)
        )
        lay.addWidget(btn)

    add_micro_btn("µ←", -1, 0)
    add_micro_btn("µ→", +1, 0)
    add_micro_btn("µ↑", 0, -1)
    add_micro_btn("µ↓", 0, +1)

    lay.addStretch(1)

    # 👉 right-aligned info group (label is right-aligned too)
    rg = right_group(w)
    rg_lay = rg.layout()
    info = QtWidgets.QLabel("")
    info.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    rg_lay.addWidget(info)

    def refresh_info() -> None:
        info.setText(f"Step {canvas.step:.1f}px | µ {canvas.micro_step:.2f}px")

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
            refresh_info()

    rg_lay.addWidget(gear_button(mw, open_settings))
    lay.addWidget(rg)

    refresh_info()
    return w
