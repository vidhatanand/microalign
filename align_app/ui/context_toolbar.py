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

    # 👉 requested separator after tabs
    tb.addSeparator()

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

    # Default
    mw._current_ctx = None
    mw.ctx_actions["move"].setChecked(True)
    _set_context(mw, "move")


def _set_context(mw, name: str) -> None:
    mw._current_ctx = name
    mw.ctx_stack.setCurrentIndex(mw.ctx_index.get(name, 0))

    # 👉 editing-only: keep warp applied even when not editing
    set_edit = getattr(mw.canvas, "set_perspective_editing", None)
    if callable(set_edit):
        set_edit(name == "perspective")
    else:
        # fallback for older canvases
        set_mode = getattr(mw.canvas, "set_perspective_mode", None)
        if callable(set_mode):
            set_mode(name == "perspective")
