from __future__ import annotations

from typing import List

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module


def build_context_toolbar(mw) -> None:
    """Construct the context toolbar and all grouped controls on the MainWindow."""
    tb = mw.toolbar_ctx
    tb.clear()

    # -- Context selector (exclusive)
    mw.ctx_group = QtWidgets.QActionGroup(mw)
    mw.ctx_group.setExclusive(True)
    mw.ctx_actions = {}

    def _add_ctx(name: str, text: str) -> None:
        act = QtWidgets.QAction(text, mw, checkable=True)
        act.triggered.connect(lambda _c=False, n=name: mw._set_context(n))
        mw.ctx_group.addAction(act)
        tb.addAction(act)
        mw.ctx_actions[name] = act

    for name, text in [
        ("move", "Move"),
        ("rotate", "Rotate"),
        ("zoom", "Zoom"),
        ("perspective", "Perspective"),
        ("grid", "Grid"),
        ("crop", "Crop"),
    ]:
        _add_ctx(name, text)

    mw.ctx_actions["move"].setChecked(True)
    mw.active_context = "move"

    tb.addSeparator()

    def _add_label(text: str) -> QtWidgets.QAction:
        lbl = QtWidgets.QLabel(text)
        lbl.setFont(tb.font())
        return tb.addWidget(lbl)

    def _add_button(text: str, slot) -> QtWidgets.QAction:
        btn = QtWidgets.QToolButton()
        btn.setText(text)
        btn.clicked.connect(slot)
        return tb.addWidget(btn)

    # ---- Move controls ----
    mw.ctrl_move: List[QtWidgets.QAction] = []
    mw.ctrl_move.append(_add_label("Move:"))

    def move(dx: float, dy: float) -> None:
        mw.canvas.move_dxdy(dx * mw.canvas.step, dy * mw.canvas.step)

    for label, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
        a = _add_button(label, lambda _c=False, dx=dx, dy=dy: move(dx, dy))
        mw.ctrl_move.append(a)

    # ---- Rotate controls ----
    mw.ctrl_rotate: List[QtWidgets.QAction] = []
    mw.ctrl_rotate.append(_add_label("Rotate:"))
    mw.ctrl_rotate.append(
        _add_button("Rot−", lambda: mw.canvas.rotate_deg(-mw.canvas.rot_step))
    )
    mw.ctrl_rotate.append(
        _add_button("Rot+", lambda: mw.canvas.rotate_deg(+mw.canvas.rot_step))
    )

    # ---- Zoom controls ----
    mw.ctrl_zoom: List[QtWidgets.QAction] = []
    mw.ctrl_zoom.append(_add_label("Zoom:"))
    mw.ctrl_zoom.append(
        _add_button("Zoom−", lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.scale_step))
    )
    mw.ctrl_zoom.append(
        _add_button("Zoom+", lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.scale_step))
    )
    mw.ctrl_zoom.append(
        _add_button(
            "µZoom−", lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.micro_scale_step)
        )
    )
    mw.ctrl_zoom.append(
        _add_button(
            "µZoom+", lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.micro_scale_step)
        )
    )

    # ---- Perspective controls ----
    mw.ctrl_persp: List[QtWidgets.QAction] = []
    mw._persp_corners_label = _add_label("Corners:")
    mw.ctrl_persp.append(mw._persp_corners_label)

    # Corner icons: TL, TR, BR, BL
    corner_icons = [
        ("┌", "Top-Left"),
        ("┐", "Top-Right"),
        ("┘", "Bottom-Right"),
        ("└", "Bottom-Left"),
    ]
    mw.corner_actions: List[QtWidgets.QAction] = []
    for i, (glyph, tip) in enumerate(corner_icons):
        act = QtWidgets.QAction(glyph, mw, checkable=True)
        act.setToolTip(tip)
        act.triggered.connect(lambda _c=False, i=i: mw._set_active_corner(i))
        tb.addAction(act)
        mw.corner_actions.append(act)
        mw.ctrl_persp.append(act)
        if i == 0:
            act.setChecked(True)

    mw.ctrl_persp.append(_add_label("Nudge:"))

    def nudge(dx: float, dy: float) -> None:
        mw.canvas.nudge_corner(dx * mw.canvas.persp_step, dy * mw.canvas.persp_step)

    for label, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
        a = _add_button(label, lambda _c=False, dx=dx, dy=dy: nudge(dx, dy))
        mw.ctrl_persp.append(a)

    # ---- Grid controls ----
    mw.ctrl_grid: List[QtWidgets.QAction] = []
    mw.ctrl_grid.append(_add_label("Grid:"))

    mw.act_grid_on = QtWidgets.QAction("Show Grid", mw, checkable=True)
    mw.act_grid_on.setChecked(mw.canvas.grid_on)
    mw.act_grid_on.toggled.connect(mw._toggle_grid_checked)
    tb.addAction(mw.act_grid_on)
    mw.ctrl_grid.append(mw.act_grid_on)

    mw.ctrl_grid.append(tb.addSeparator())

    mw.ctrl_grid.append(_add_label("Step:"))
    mw.grid_step_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    mw.grid_step_slider.setMinimum(8)
    mw.grid_step_slider.setMaximum(200)
    mw.grid_step_slider.setValue(int(mw.canvas.grid_step))
    mw.grid_step_slider.setFixedWidth(160)
    mw.grid_step_slider.valueChanged.connect(mw._on_grid_step_change)
    mw.ctrl_grid.append(tb.addWidget(mw.grid_step_slider))

    mw.grid_step_value = QtWidgets.QLabel(str(int(mw.canvas.grid_step)))
    mw.grid_step_value.setFont(tb.font())
    mw.ctrl_grid.append(tb.addWidget(mw.grid_step_value))

    # ---- Crop controls ----
    mw.ctrl_crop: List[QtWidgets.QAction] = []
    mw.ctrl_crop.append(_add_label("Crop Source:"))

    # radio buttons (Source, Aligned)
    crop_src_widget = QtWidgets.QWidget()
    crop_src_layout = QtWidgets.QHBoxLayout(crop_src_widget)
    crop_src_layout.setContentsMargins(0, 0, 0, 0)

    mw.crop_radio_source = QtWidgets.QRadioButton("Source")
    mw.crop_radio_aligned = QtWidgets.QRadioButton("Aligned")
    mw.crop_radio_source.setFont(tb.font())
    mw.crop_radio_aligned.setFont(tb.font())

    # initial selection from canvas state
    if getattr(mw.canvas, "crop_from_aligned", True):
        mw.crop_radio_aligned.setChecked(True)
    else:
        mw.crop_radio_source.setChecked(True)

    crop_src_layout.addWidget(mw.crop_radio_source)
    crop_src_layout.addWidget(mw.crop_radio_aligned)
    mw.ctrl_crop.append(tb.addWidget(crop_src_widget))

    mw.ctrl_crop.append(tb.addSeparator())
    mw.ctrl_crop.append(_add_button("Start", mw._start_crop_clicked))

    # Spacer + right-edge dynamic value label
    spacer = QtWidgets.QWidget()
    spacer.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
    )
    tb.addWidget(spacer)
    mw.ctx_value_label = QtWidgets.QLabel("")
    mw.ctx_value_label.setFont(tb.font())
    mw.ctx_value_label.setStyleSheet("QLabel { color: #ddd; padding-right: 6px; }")
    tb.addWidget(mw.ctx_value_label)

    # Initial show/hide + label
    mw._refresh_context_ui()
    mw._refresh_context_value_label()
