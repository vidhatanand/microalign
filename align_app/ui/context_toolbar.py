from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore


def _row_container(font) -> QtWidgets.QWidget:
    """Return a horizontal container with tight spacing and toolbar font."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    w.setFont(font)
    return w


def _build_move_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Move:"))
    for label, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
        btn = QtWidgets.QToolButton()
        btn.setText(label)
        btn.clicked.connect(
            lambda _=False, dx=dx, dy=dy: mw.canvas.move_dxdy(
                dx * mw.canvas.step, dy * mw.canvas.step
            )
        )
        lay.addWidget(btn)
    step_spin = QtWidgets.QDoubleSpinBox()
    step_spin.setDecimals(1)
    step_spin.setSingleStep(0.5)
    step_spin.setRange(0.5, 50.0)
    step_spin.setValue(mw.canvas.step)
    step_spin.valueChanged.connect(lambda v: setattr(mw.canvas, "step", float(v)))
    lay.addWidget(QtWidgets.QLabel("Step:"))
    lay.addWidget(step_spin)
    return w


def _build_rotate_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Rotate:"))
    btn_rminus = QtWidgets.QToolButton()
    btn_rminus.setText("Rot−")
    btn_rplus = QtWidgets.QToolButton()
    btn_rplus.setText("Rot+")
    btn_rminus.clicked.connect(lambda: mw.canvas.rotate_deg(-mw.canvas.rot_step))
    btn_rplus.clicked.connect(lambda: mw.canvas.rotate_deg(+mw.canvas.rot_step))
    lay.addWidget(btn_rminus)
    lay.addWidget(btn_rplus)
    rs = QtWidgets.QDoubleSpinBox()
    rs.setDecimals(2)
    rs.setSingleStep(0.05)
    rs.setRange(0.01, 5.0)
    rs.setSuffix("°")
    rs.setValue(mw.canvas.rot_step)
    rs.valueChanged.connect(lambda v: setattr(mw.canvas, "rot_step", float(v)))
    lay.addWidget(QtWidgets.QLabel("Step:"))
    lay.addWidget(rs)
    return w


def _build_zoom_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Zoom (image):"))
    btn_zminus = QtWidgets.QToolButton()
    btn_zminus.setText("Zoom−")
    btn_zplus = QtWidgets.QToolButton()
    btn_zplus.setText("Zoom+")
    btn_mzminus = QtWidgets.QToolButton()
    btn_mzminus.setText("µZoom−")
    btn_mzplus = QtWidgets.QToolButton()
    btn_mzplus.setText("µZoom+")
    btn_zminus.clicked.connect(
        lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.scale_step)
    )
    btn_zplus.clicked.connect(lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.scale_step))
    btn_mzminus.clicked.connect(
        lambda: mw.canvas.zoom_factor(1.0 - mw.canvas.micro_scale_step)
    )
    btn_mzplus.clicked.connect(
        lambda: mw.canvas.zoom_factor(1.0 + mw.canvas.micro_scale_step)
    )
    for b in (btn_zminus, btn_zplus, btn_mzminus, btn_mzplus):
        lay.addWidget(b)
    zs = QtWidgets.QDoubleSpinBox()
    zs.setDecimals(3)
    zs.setSingleStep(0.001)
    zs.setRange(0.001, 0.05)
    zs.setValue(mw.canvas.scale_step)
    zs.valueChanged.connect(lambda v: setattr(mw.canvas, "scale_step", float(v)))
    mzs = QtWidgets.QDoubleSpinBox()
    mzs.setDecimals(3)
    mzs.setSingleStep(0.001)
    mzs.setRange(0.0005, 0.02)
    mzs.setValue(mw.canvas.micro_scale_step)
    mzs.valueChanged.connect(lambda v: setattr(mw.canvas, "micro_scale_step", float(v)))
    lay.addWidget(QtWidgets.QLabel("Step:"))
    lay.addWidget(zs)
    lay.addWidget(QtWidgets.QLabel("µ:"))
    lay.addWidget(mzs)
    return w


def _build_perspective_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    lay.addWidget(QtWidgets.QLabel("Corners:"))
    # ⌜ ⌝ ⌟ ⌞
    for i, ch in enumerate(("⌜", "⌝", "⌟", "⌞")):
        btn = QtWidgets.QToolButton()
        btn.setText(ch)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _=False, i=i: mw.canvas.set_active_corner(i))
        lay.addWidget(btn)
    for label, dx, dy in [("←", -1, 0), ("→", +1, 0), ("↑", 0, -1), ("↓", 0, +1)]:
        btn = QtWidgets.QToolButton()
        btn.setText(label)
        btn.clicked.connect(
            lambda _=False, dx=dx, dy=dy: mw.canvas.nudge_corner(
                dx * mw.canvas.persp_step, dy * mw.canvas.persp_step
            )
        )
        lay.addWidget(btn)
    ps = QtWidgets.QDoubleSpinBox()
    ps.setDecimals(1)
    ps.setSingleStep(0.5)
    ps.setRange(0.5, 50.0)
    ps.setValue(mw.canvas.persp_step)
    ps.valueChanged.connect(lambda v: setattr(mw.canvas, "persp_step", float(v)))
    lay.addWidget(QtWidgets.QLabel("Step:"))
    lay.addWidget(ps)
    return w


def _build_grid_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    cb = QtWidgets.QCheckBox("Show Grid")
    cb.setChecked(mw.canvas.grid_on)
    cb.toggled.connect(
        lambda v: (setattr(mw.canvas, "grid_on", bool(v)), mw.canvas.update())
    )
    lay.addWidget(cb)
    sp = QtWidgets.QSpinBox()
    sp.setRange(5, 400)
    sp.setValue(mw.canvas.grid_step)
    sp.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "grid_step", int(v)), mw.canvas.update())
    )
    lay.addWidget(QtWidgets.QLabel("Step:"))
    lay.addWidget(sp)
    return w


def _build_crop_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
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


def _build_overlay_group(mw) -> QtWidgets.QWidget:
    w = _row_container(mw.toolbar_bottom.font())
    lay = w.layout()
    cb_overlay = QtWidgets.QCheckBox("Overlay")
    cb_overlay.setChecked(mw.canvas.overlay_mode)
    cb_overlay.toggled.connect(
        lambda v: (setattr(mw.canvas, "overlay_mode", bool(v)), mw.canvas.update())
    )
    cb_outline = QtWidgets.QCheckBox("Outline")
    cb_outline.setChecked(mw.canvas.show_outline)
    cb_outline.toggled.connect(
        lambda v: (setattr(mw.canvas, "show_outline", bool(v)), mw.canvas.update())
    )
    lay.addWidget(cb_overlay)
    lay.addWidget(cb_outline)

    lay.addWidget(QtWidgets.QLabel("Alpha:"))
    sld = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    sld.setRange(0, 100)
    sld.setFixedWidth(160)
    sld.setValue(int(round(mw.canvas.alpha * 100)))
    sld.valueChanged.connect(
        lambda v: (setattr(mw.canvas, "alpha", v / 100.0), mw.canvas.update())
    )
    lay.addWidget(sld)
    return w


def build_context_toolbar(mw) -> None:
    tb = mw.toolbar_bottom
    tb.clear()

    # ---- Tab actions (use QActions so toolbar overflow chevron works) ----
    mw.ctx_group = QtWidgets.QActionGroup(mw)
    mw.ctx_group.setExclusive(True)
    mw.ctx_actions = {}

    def add_tab(name: str, label: str) -> None:
        act = QtWidgets.QAction(label, mw, checkable=True)
        act.setData(name)
        mw.ctx_group.addAction(act)
        tb.addAction(act)
        mw.ctx_actions[name] = act
        act.toggled.connect(lambda checked, n=name: checked and _set_context(mw, n))

    # Order matters
    add_tab("move", "Move")
    add_tab("rotate", "Rotate")
    add_tab("zoom", "Zoom")
    add_tab("perspective", "Perspective")
    add_tab("grid", "Grid")
    add_tab("crop", "Crop")
    add_tab("overlay", "Overlay")

    tb.addSeparator()

    # ---- Single stacked panel with per-tab groups (only one widget is present) ----
    mw.ctx_stack = QtWidgets.QStackedWidget()
    mw.ctx_stack.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
    )

    mw.ctx_builders = {
        "move": _build_move_group,
        "rotate": _build_rotate_group,
        "zoom": _build_zoom_group,
        "perspective": _build_perspective_group,
        "grid": _build_grid_group,
        "crop": _build_crop_group,
        "overlay": _build_overlay_group,
    }
    mw.ctx_index = {}

    # Build and add each group once
    for i, name in enumerate(mw.ctx_builders.keys()):
        panel = mw.ctx_builders[name](mw)
        mw.ctx_stack.addWidget(panel)
        mw.ctx_index[name] = i

    # Put the stack into the toolbar as a QWidgetAction, which behaves better with overflow
    stack_action = QtWidgets.QWidgetAction(mw)
    stack_action.setDefaultWidget(mw.ctx_stack)
    tb.addAction(stack_action)

    # ---- "More…" button to show full controls in a popup when space is tight ----
    mw.ctx_more_btn = QtWidgets.QToolButton()
    mw.ctx_more_btn.setText("…")
    mw.ctx_more_btn.setToolTip("Show controls in a popup")

    def _show_more():
        # Build a fresh panel for the current tab so we don't reparent the live one
        name = mw._current_ctx or "move"
        panel = mw.ctx_builders[name](mw)
        dlg = QtWidgets.QDialog(mw)
        dlg.setWindowTitle(f"{name.capitalize()} controls")
        v = QtWidgets.QVBoxLayout(dlg)
        sv = QtWidgets.QScrollArea()
        sv.setWidgetResizable(True)
        host = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(host)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(panel)
        sv.setWidget(host)
        v.addWidget(sv)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.resize(480, 200)
        dlg.exec_()

    mw.ctx_more_btn.clicked.connect(_show_more)
    tb.addWidget(mw.ctx_more_btn)

    # ---- Info label at the far right ----
    tb.addSeparator()
    mw.ctx_info = QtWidgets.QLabel("")
    mw.ctx_info.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
    mw.ctx_info.setMinimumWidth(240)
    mw.ctx_info.setFont(tb.font())
    tb.addWidget(mw.ctx_info)

    # Default tab
    mw._current_ctx = None
    mw.ctx_actions["move"].setChecked(True)
    _set_context(mw, "move")


def _set_context(mw, name: str) -> None:
    mw._current_ctx = name
    # Show the correct panel
    idx = mw.ctx_index.get(name, 0)
    mw.ctx_stack.setCurrentIndex(idx)

    # Sync canvas mode (only Perspective tab toggles perspective mode)
    mw.canvas.set_perspective_mode(name == "perspective")

    # Contextual info text
    if name == "move":
        mw.ctx_info.setText(f"Move step: {mw.canvas.step:.1f}px")
    elif name == "rotate":
        mw.ctx_info.setText(f"Rotate step: {mw.canvas.rot_step:.2f}°")
    elif name == "zoom":
        z = mw.canvas.scale_step * 100.0
        mz = mw.canvas.micro_scale_step * 100.0
        mw.ctx_info.setText(f"Zoom step: ±{z:.2f}% (µ {mz:.2f}%)")
    elif name == "perspective":
        mw.ctx_info.setText(f"Corner step: {mw.canvas.persp_step:.1f}px")
    elif name == "grid":
        mw.ctx_info.setText(f"Grid step: {mw.canvas.grid_step}px")
    elif name == "crop":
        mw.ctx_info.setText("Drag on Base to crop")
    elif name == "overlay":
        mw.ctx_info.setText(
            f"Alpha: {mw.canvas.alpha:.2f}  (Overlay {'On' if mw.canvas.overlay_mode else 'Off'})"
        )
