"""Main window: path + nav on row 1, context selector on row 2.

Row 1 (Top): Sidebar toggle + Paths + Overlay/Outline + Collective View Zoom (− / slider / + / reset / Hand)
             + Alpha + Navigation (Prev / Next / Save / Save+Next) + Undo / Redo / Reset

Row 2 (Context bar): Context selector (exclusive) + ONLY that group's controls:
  - Move: arrow buttons (uses canvas.step)
  - Rotate: Rot− / Rot+
  - Zoom: Zoom− / Zoom+ / µZoom− / µZoom+
  - Perspective: "Corners:" + corner icons (┌ ┐ ┘ └) + arrow nudge (uses canvas.persp_step)
  - Grid: "Show Grid" + Step slider + live value
  - Crop: "Crop Source:" + radio [Source, Aligned] + Start

Status bar: left empty (kept only for the progress bar on the right).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets  # pylint: disable=no-name-in-module

from align_app.ui.align_canvas import AlignCanvas
from align_app.utils.img_io import SUPPORTED_LOWER, clamp
from .sidebar import build_sidebar, highlight_current_in_sidebar
from .watchers import rebuild_watchers
from .top_toolbar import build_top_toolbar
from .context_toolbar import build_context_toolbar


class MainWindow(QtWidgets.QMainWindow):
    """Main application window wiring canvas and toolbars."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroAlign")
        self.resize(1400, 900)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.setCentralWidget(self.splitter)

        # Left: compact sidebar (collapsible)
        self.sidebar = QtWidgets.QTreeWidget()
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setMinimumWidth(220)
        self._sidebar_last_w = 320
        self.splitter.addWidget(self.sidebar)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        # Right: toolbars + canvas (two rows)
        right = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)

        self.toolbar_top = QtWidgets.QToolBar("Top")
        self.toolbar_ctx = QtWidgets.QToolBar("Context")
        for tb in (self.toolbar_top, self.toolbar_ctx):
            tb.setIconSize(QtCore.QSize(20, 20))

        layout.addWidget(self.toolbar_top)
        layout.addWidget(self.toolbar_ctx)

        self.canvas = AlignCanvas()
        layout.addWidget(self.canvas, 1)

        self.splitter.addWidget(right)
        self.splitter.setSizes([350, 1050])

        # Build toolbars (helpers)
        build_top_toolbar(self)
        build_context_toolbar(self)

        # Sidebar interactions
        self.sidebar.itemDoubleClicked.connect(self._sidebar_double_clicked)

        # Status bar + progress (no text label)
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedWidth(220)
        self.status.addPermanentWidget(self.progress)

        # File/folder watcher
        self.watcher = QtCore.QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._fs_changed)
        self.watcher.fileChanged.connect(self._fs_changed)
        self._fs_timer = QtCore.QTimer(self)
        self._fs_timer.setSingleShot(True)
        self._fs_timer.timeout.connect(lambda: self._fs_refresh())

        # Canvas signals
        self.canvas.currentPathChanged.connect(
            lambda _p: highlight_current_in_sidebar(self.sidebar, self.canvas)
        )
        self.canvas.cropProgress.connect(self._on_crop_progress)
        self.canvas.modeChanged.connect(self._on_canvas_mode_changed)
        self.canvas.activeCornerChanged.connect(self._sync_corner_buttons)

        # Initial sidebar + watchers
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- sidebar collapse ----------

    def _toggle_sidebar(self, checked: bool) -> None:
        # show/hide and adjust splitter sizes
        if checked:
            self.sidebar.setVisible(True)
            total = max(1, self.splitter.width())
            left = max(180, self._sidebar_last_w)
            self.splitter.setSizes([left, total - left])
        else:
            self._sidebar_last_w = self.sidebar.width()
            self.sidebar.setVisible(False)
            total = max(1, self.splitter.width())
            self.splitter.setSizes([0, total])

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self.sidebar.isVisible():
            self._sidebar_last_w = self.sidebar.width()

    # ---------- top toolbar handlers ----------

    def toggle_overlay(self) -> None:
        self.canvas.overlay_mode = not self.canvas.overlay_mode
        self.canvas.update()

    def toggle_outline(self) -> None:
        self.canvas.show_outline = not self.canvas.show_outline
        self.canvas.update()

    def _on_zoom_slider(self, value: int) -> None:
        """Slider handler: set collective view zoom (top-left anchored)."""
        self.canvas.view_zoom = value / 100.0
        self.canvas.update()

    def _bump_view_zoom(self, delta: float) -> None:
        """Minus/Plus buttons: nudge collective view zoom and sync slider."""
        v = clamp(self.canvas.view_zoom + delta, 0.25, 5.0)
        if hasattr(self, "zoom_slider"):
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(int(round(v * 100)))
            self.zoom_slider.blockSignals(False)
        self.canvas.view_zoom = v
        self.canvas.update()

    def _reset_view_zoom(self) -> None:
        if hasattr(self, "zoom_slider"):
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(100)
            self.zoom_slider.blockSignals(False)
        self.canvas.view_zoom = 1.0
        self.canvas.update()

    def _toggle_hand_pan(self, checked: bool) -> None:
        """Toggle the Hand (pan) tool for panning both panels."""
        self.canvas.set_pan_mode(bool(checked))

    # ---------- context switching + UI (row 2) ----------

    def _set_context(self, name: str) -> None:
        if name == getattr(self, "active_context", None):
            return
        self.active_context = name
        # Toggle perspective mode according to context (preserve image state)
        self.canvas.set_perspective_mode(name == "perspective")
        # Update selector checks & show/hide groups
        for n, act in getattr(self, "ctx_actions", {}).items():
            act.setChecked(n == name)
        self._refresh_context_ui()
        self._refresh_context_value_label()

    def _refresh_context_ui(self) -> None:
        """Hide all group actions, show only the selected group's controls."""
        show_map = {
            "move": getattr(self, "ctrl_move", []),
            "rotate": getattr(self, "ctrl_rotate", []),
            "zoom": getattr(self, "ctrl_zoom", []),
            "perspective": getattr(self, "ctrl_persp", []),
            "grid": getattr(self, "ctrl_grid", []),
            "crop": getattr(self, "ctrl_crop", []),
        }
        all_groups = []
        for k in show_map.values():
            all_groups += k
        for a in all_groups:
            a.setVisible(False)
        for a in show_map.get(self.active_context, []):
            a.setVisible(True)

    def _refresh_context_value_label(self) -> None:
        # Right-edge value: keep minimal (no footer status text anymore)
        c = getattr(self, "active_context", "")
        if c == "grid":
            txt = f"Grid: {'On' if self.canvas.grid_on else 'Off'}   Step: {int(self.canvas.grid_step)}"
        elif c == "crop":
            choice = (
                "Aligned"
                if (
                    hasattr(self, "crop_radio_aligned")
                    and self.crop_radio_aligned.isChecked()
                )
                else "Source"
            )
            txt = f"Crop Source: {choice}"
        elif c == "perspective":
            txt = f"Corner: {self.canvas.active_corner+1}"
        else:
            txt = ""
        if hasattr(self, "ctx_value_label"):
            self.ctx_value_label.setText(txt)

    def _toggle_grid_checked(self, state: bool) -> None:
        self.canvas.grid_on = bool(state)
        self.canvas.update()
        self._refresh_context_value_label()

    def _on_grid_step_change(self, value: int) -> None:
        self.canvas.grid_step = int(value)
        if hasattr(self, "grid_step_value"):
            self.grid_step_value.setText(str(int(value)))
        self.canvas.update()
        self._refresh_context_value_label()

    def _start_crop_clicked(self) -> None:
        use_aligned = False
        if hasattr(self, "crop_radio_aligned") and self.crop_radio_aligned.isChecked():
            use_aligned = True
        self.canvas.start_crop_mode(use_aligned)
        self._refresh_context_value_label()

    def _set_active_corner(self, idx: int) -> None:
        self.canvas.set_active_corner(idx)
        self._sync_corner_buttons(idx)

    # ---------- sync from canvas signals ----------

    def _on_canvas_mode_changed(self, is_persp: bool) -> None:
        # If user hit 'P', switch context accordingly without changing image state.
        if is_persp:
            self._set_context("perspective")
        elif getattr(self, "active_context", "") == "perspective":
            self._set_context("move")

    def _sync_corner_buttons(self, idx: int) -> None:
        if hasattr(self, "corner_actions"):
            for i, act in enumerate(self.corner_actions):
                act.setChecked(i == idx)
        self._refresh_context_value_label()

    # ---------- pickers ----------

    def _pick_base_image(self) -> None:
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose Base Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.jpe)",
        )
        if fn:
            self.canvas.set_paths(
                base_path=Path(fn), src_dir=None, align_out=None, crop_out=None
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    def _pick_src_dir(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Source Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=Path(d), align_out=None, crop_out=None
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    def _pick_align_out(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Align Out Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=None, align_out=Path(d), crop_out=None
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    def _pick_crop_out(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose Crops Out Directory", str(Path.home())
        )
        if d:
            self.canvas.set_paths(
                base_path=None, src_dir=None, align_out=None, crop_out=Path(d)
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    def _reload_all(self) -> None:
        self.canvas.set_paths(
            self.canvas.base_path,
            self.canvas.src_dir,
            self.canvas.align_out,
            self.canvas.crop_out,
        )
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- sidebar ----------

    def _sidebar_double_clicked(
        self, item: QtWidgets.QTreeWidgetItem, _col: int
    ) -> None:
        path = item.data(0, QtCore.Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if p.is_file() and p.suffix.lower() in SUPPORTED_LOWER:
            if self.canvas.files:
                try:
                    idx = self.canvas.files.index(p)
                except ValueError:
                    idx = None
                if idx is not None:
                    self.canvas.idx = idx
                    self.canvas.update()
                    highlight_current_in_sidebar(self.sidebar, self.canvas)
        elif p.is_dir():
            self.canvas.set_paths(
                base_path=None, src_dir=p, align_out=None, crop_out=None
            )
            build_sidebar(self.sidebar, self.canvas)
            rebuild_watchers(self.watcher, self.canvas)
            highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- filesystem watching ----------

    def _fs_changed(self, _path: str) -> None:
        self._fs_timer.start(250)

    def _fs_refresh(self) -> None:
        cur = self.canvas.current_path()
        self.canvas.set_paths(
            self.canvas.base_path,
            self.canvas.src_dir,
            self.canvas.align_out,
            self.canvas.crop_out,
        )
        if cur and cur in self.canvas.files:
            try:
                self.canvas.idx = self.canvas.files.index(cur)
            except ValueError:
                pass
        build_sidebar(self.sidebar, self.canvas)
        rebuild_watchers(self.watcher, self.canvas)
        highlight_current_in_sidebar(self.sidebar, self.canvas)

    # ---------- crop progress ----------

    def _on_crop_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.setVisible(False)
            return
        self.progress.setVisible(True)
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        if done >= total:
            # small delay to show 100%
            QtCore.QTimer.singleShot(600, lambda: self.progress.setVisible(False))
