from __future__ import annotations

from PyQt5 import QtCore, QtWidgets  # type: ignore

from .context_panels.move import build as build_move_panel
from .context_panels.rotate import build as build_rotate_panel
from .context_panels.zoom import build as build_zoom_panel
from .context_panels.perspective import build as build_perspective_panel
from .context_panels.grid import build as build_grid_panel
from .context_panels.crop import build as build_crop_panel
from .context_panels.overlay import build as build_overlay_panel


def build_context_toolbar(mw) -> None:
    tb = mw.toolbar_bottom
    tb.clear()

    # ---- Tab actions ----
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

    add_tab("move", "Move")
    add_tab("rotate", "Rotate")
    add_tab("zoom", "Zoom")
    add_tab("perspective", "Perspective")
    add_tab("grid", "Grid")
    add_tab("crop", "Crop")
    add_tab("overlay", "Overlay")

    # ---- Stacked controls (left-aligned) ----
    mw.ctx_stack = QtWidgets.QStackedWidget()
    mw.ctx_builders = {
        "move": build_move_panel,
        "rotate": build_rotate_panel,
        "zoom": build_zoom_panel,
        "perspective": build_perspective_panel,
        "grid": build_grid_panel,
        "crop": build_crop_panel,
        "overlay": build_overlay_panel,
    }
    mw.ctx_index = {}
    for i, name in enumerate(mw.ctx_builders.keys()):
        panel = mw.ctx_builders[name](mw)
        mw.ctx_stack.addWidget(panel)
        mw.ctx_index[name] = i

    host = QtWidgets.QWidget()
    hlay = QtWidgets.QHBoxLayout(host)
    hlay.setContentsMargins(0, 0, 0, 0)
    hlay.setSpacing(0)
    hlay.setAlignment(QtCore.Qt.AlignLeft)
    hlay.addWidget(mw.ctx_stack)
    hlay.addStretch(1)
    stack_action = QtWidgets.QWidgetAction(mw)
    stack_action.setDefaultWidget(host)
    tb.addAction(stack_action)

    # ---- Info label ----
    tb.addSeparator()
    mw.ctx_info = QtWidgets.QLabel("")
    mw.ctx_info.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
    mw.ctx_info.setMinimumWidth(240)
    mw.ctx_info.setFont(tb.font())
    tb.addWidget(mw.ctx_info)

    # Provide a helper so panels can refresh the info label after settings change.
    def _update_ctx_info() -> None:
        name = mw._current_ctx or "move"
        if name == "move":
            step = getattr(mw.canvas, "step", 1.0)
            micro = getattr(mw.canvas, "micro_step", max(0.05, step / 4.0))
            mw.ctx_info.setText(f"Move step: {step:.1f}px (µ {micro:.2f}px)")
        elif name == "rotate":
            r = getattr(mw.canvas, "rot_step", 0.25)
            mr = getattr(mw.canvas, "micro_rot_step", max(0.001, r / 4.0))
            mw.ctx_info.setText(f"Rotate step: {r:.2f}° (µ {mr:.3f}°)")
        elif name == "zoom":
            z = getattr(mw.canvas, "scale_step", 0.01) * 100.0
            mz = getattr(mw.canvas, "micro_scale_step", 0.005) * 100.0
            mw.ctx_info.setText(f"Zoom step: ±{z:.2f}% (µ {mz:.2f}%)")
        elif name == "perspective":
            p = getattr(mw.canvas, "persp_step", 1.0)
            mw.ctx_info.setText(f"Corner step: {p:.1f}px")
        elif name == "grid":
            g = getattr(mw.canvas, "grid_step", 20)
            mw.ctx_info.setText(f"Grid step: {g}px")
        elif name == "crop":
            mw.ctx_info.setText("Drag on Base to crop")
        elif name == "overlay":
            onoff = "On" if getattr(mw.canvas, "overlay_mode", False) else "Off"
            alpha = getattr(mw.canvas, "alpha", 0.5)
            mw.ctx_info.setText(f"Alpha: {alpha:.2f}  (Overlay {onoff})")

    mw._update_ctx_info = _update_ctx_info  # type: ignore[attr-defined]

    # Default
    mw._current_ctx = None
    mw.ctx_actions["move"].setChecked(True)
    _set_context(mw, "move")


def _set_context(mw, name: str) -> None:
    mw._current_ctx = name
    mw.ctx_stack.setCurrentIndex(mw.ctx_index.get(name, 0))
    mw.canvas.set_perspective_mode(name == "perspective")
    # refresh info using the helper panels also use
    mw._update_ctx_info()  # type: ignore[attr-defined]
