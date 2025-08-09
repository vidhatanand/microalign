from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .common import row_container, gear_button, label, right_group


def build(mw) -> QtWidgets.QWidget:
    w = row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(label("Perspective", w.font()))

    group = QtWidgets.QButtonGroup(mw)
    group.setExclusive(True)
    mw._persp_btn_group = group
    mw._persp_btns = []

    for i, ch in enumerate(("⌜", "⌝", "⌟", "⌞")):
        btn = QtWidgets.QToolButton()
        btn.setText(ch)
        btn.setCheckable(True)
        group.addButton(btn, i)
        lay.addWidget(btn)
        mw._persp_btns.append(btn)

    def _sync_corner(idx: int) -> None:
        b = group.button(idx)
        if b and not b.isChecked():
            b.setChecked(True)

    mw.canvas.activeCornerChanged.connect(_sync_corner)
    _sync_corner(mw.canvas.active_corner)

    group.idToggled.connect(
        lambda idx, checked: checked and mw.canvas.set_active_corner(idx)
    )

    for txt, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
        btn = QtWidgets.QToolButton()
        btn.setText(txt)
        btn.clicked.connect(
            lambda _=False, dx=dx, dy=dy: mw.canvas.nudge_corner(
                dx * mw.canvas.persp_step, dy * mw.canvas.persp_step
            )
        )
        lay.addWidget(btn)

    lay.addStretch(1)

    rg = right_group(w)
    rg_lay = rg.layout()
    info = QtWidgets.QLabel("")
    info.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    rg_lay.addWidget(info)

    def refresh_info() -> None:
        info.setText(f"Step {mw.canvas.persp_step:.1f}px")

    def open_settings() -> None:
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle("Perspective settings")
        form = QtWidgets.QFormLayout(dlg)

        ps = QtWidgets.QDoubleSpinBox()
        ps.setDecimals(1)
        ps.setSingleStep(0.5)
        ps.setRange(0.5, 50.0)
        ps.setValue(mw.canvas.persp_step)

        form.addRow("Corner step (px):", ps)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            mw.canvas.persp_step = float(ps.value())
            refresh_info()

    rg_lay.addWidget(gear_button(mw, open_settings))
    lay.addWidget(rg)

    refresh_info()
    return w
